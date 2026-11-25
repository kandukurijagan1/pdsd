/**
 * whatsapp_service/service.js
 * Production-Grade WhatsApp Web QR Authentication & Dispatch Microservice
 * Configured with exact Chrome User-Agent and Cached WhatsApp Web version
 * to completely eliminate WhatsApp's "Couldn't link device. Try again later." error.
 */

const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const qrcode = require('qrcode');
const multer = require('multer');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
let puppeteerExtra = null;
try {
    puppeteerExtra = require('puppeteer-extra');
    const StealthPlugin = require('puppeteer-extra-plugin-stealth');
    puppeteerExtra.use(StealthPlugin());
    console.log('[WhatsApp Service] Puppeteer Stealth plugin activated successfully.');
} catch (eStealth) {
    console.warn('[WhatsApp Service] Stealth plugin fallback:', eStealth.message);
}

// Global safety net: Prevent crashes from unhandled rejections or closed targets
process.on('unhandledRejection', (reason, promise) => {
    console.warn('[WhatsApp Service] Handled unhandledRejection safely:', reason ? (reason.message || reason) : 'Unknown');
});
process.on('uncaughtException', (err) => {
    console.warn('[WhatsApp Service] Handled uncaughtException safely:', err ? (err.message || err) : 'Unknown');
});

const app = express();
const PORT = process.env.PORT || 3005;

app.use(cors());
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

const upload = multer({ dest: path.join(__dirname, 'uploads') });
if (!fs.existsSync(path.join(__dirname, 'uploads'))) {
    fs.mkdirSync(path.join(__dirname, 'uploads'), { recursive: true });
}

let client = null;
let qrCodeDataUrl = null;
let lastPairingCode = null;
let isConnected = false;
let isInitializing = false;
let userInfo = null;
let lastError = null;

const AUTH_DIR = path.join(__dirname, '.wwebjs_auth');
const USER_INFO_FILE = path.join(__dirname, 'session_user.json');

function saveSavedUserInfo(info) {
    try {
        fs.writeFileSync(USER_INFO_FILE, JSON.stringify(info, null, 2), 'utf8');
    } catch (e) {
        console.error('Failed to save session user info:', e.message);
    }
}

function getSavedUserInfo() {
    try {
        if (fs.existsSync(USER_INFO_FILE)) {
            return JSON.parse(fs.readFileSync(USER_INFO_FILE, 'utf8'));
        }
    } catch (e) {}
    return null;
}

function cleanChromeLocks() {
    const lockFiles = [
        path.join(AUTH_DIR, 'session', 'lockfile'),
        path.join(AUTH_DIR, 'session', 'SingletonLock'),
        path.join(AUTH_DIR, 'session', 'SingletonCookie'),
        path.join(AUTH_DIR, 'session', 'SingletonSocket')
    ];
    for (const lf of lockFiles) {
        try {
            if (fs.existsSync(lf)) fs.unlinkSync(lf);
        } catch (_) {}
    }
}

function findChromePath() {
    const candidates = [
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        path.join(process.env.LOCALAPPDATA || '', 'Google\\Chrome\\Application\\chrome.exe'),
        path.join(process.env.PROGRAMFILES || '', 'Google\\Chrome\\Application\\chrome.exe')
    ];
    for (const p of candidates) {
        if (fs.existsSync(p)) return p;
    }
    return undefined;
}

async function safeDestroyClient() {
    if (client) {
        try {
            if (client.pupBrowser) {
                await client.pupBrowser.close().catch(() => {});
            }
            await client.destroy().catch(() => {});
        } catch (_) {}
        client = null;
    }
    cleanChromeLocks();
}

async function initWhatsApp(forceNew = false) {
    if (isInitializing) {
        console.log('[WhatsApp Service] Already initializing...');
        return;
    }

    isInitializing = true;
    lastError = null;

    if (forceNew) {
        await safeDestroyClient();
        isConnected = false;
        qrCodeDataUrl = null;
        userInfo = null;
        if (fs.existsSync(AUTH_DIR)) {
            try {
                fs.rmSync(AUTH_DIR, { recursive: true, force: true });
            } catch (e) {
                console.warn('[WhatsApp Service] Note cleaning auth dir:', e.message);
            }
        }
        if (fs.existsSync(USER_INFO_FILE)) {
            try { fs.unlinkSync(USER_INFO_FILE); } catch (_) {}
        }
    } else {
        await safeDestroyClient();
    }

    cleanChromeLocks();
    const chromeExecutable = findChromePath();
    console.log('[WhatsApp Service] Initializing WhatsApp Client. Chrome:', chromeExecutable || 'Default Puppeteer');

    try {
        const localAuth = new LocalAuth({ dataPath: AUTH_DIR });
        localAuth.logout = async function() {
            cleanChromeLocks();
        };

        // Modern Windows Chrome User-Agent matching the system
        const userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36';

        // Check if cached WhatsApp web version is available
        const cacheDir = path.join(__dirname, '.wwebjs_cache');
        let webVersionCache = {
            type: 'remote',
            remotePath: 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.3000.1049282529-alpha.html',
            strict: false
        };
        if (fs.existsSync(cacheDir) && fs.readdirSync(cacheDir).some(f => f.endsWith('.html'))) {
            webVersionCache = {
                type: 'local',
                path: cacheDir,
                strict: false
            };
        }

        const puppeteerConfig = {
            headless: true,
            executablePath: chromeExecutable,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
                `--user-agent=${userAgent}`,
                '--window-size=1280,720'
            ]
        };

        const clientOptions = {
            authStrategy: localAuth,
            webVersionCache: webVersionCache,
            puppeteer: puppeteerConfig,
            authTimeoutMs: 120000,
            takeoverTimeoutMs: 60000,
            qrMaxRetries: 10
        };

        // Attach stealth puppeteer if available to bypass WhatsApp device link rejections
        if (puppeteerExtra) {
            clientOptions.puppeteer = {
                ...puppeteerConfig,
                ...puppeteerExtra
            };
        }

        client = new Client(clientOptions);

        client.on('qr', async (qr) => {
            console.log('[WhatsApp Service] Clean QR Code received from WhatsApp Web!');
            try {
                qrCodeDataUrl = await qrcode.toDataURL(qr, { margin: 2, scale: 6 });
                isConnected = false;
                isInitializing = false;
            } catch (err) {
                console.error('[WhatsApp Service] Error converting QR to data URL:', err);
            }
        });

        client.on('ready', async () => {
            console.log('✅ [WhatsApp Service] WhatsApp is Authenticated & Ready!');
            isConnected = true;
            isInitializing = false;
            qrCodeDataUrl = null;
            lastPairingCode = null;

            // Automatically dismiss any onboarding, changelog or welcome modals ("What's new on WhatsApp Web", "Continue", etc.)
            try {
                if (client.pupPage) {
                    await client.pupPage.evaluate(() => {
                        const btns = Array.from(document.querySelectorAll('button, div[role="button"]'));
                        for (const b of btns) {
                            const txt = (b.innerText || '').trim();
                            if (txt === 'Continue' || txt === 'OK' || txt === 'Got it' || txt === 'Done') {
                                b.click();
                            }
                        }
                    }).catch(() => {});
                }
            } catch (_) {}

            let phone = '';
            let name = 'KK Security';
            if (client.info) {
                if (client.info.wid && client.info.wid.user) phone = client.info.wid.user;
                else if (client.info.me && client.info.me.user) phone = client.info.me.user;
                if (client.info.pushname) name = client.info.pushname;
            }
            if (!phone) {
                const saved = getSavedUserInfo();
                if (saved && saved.phone) {
                    phone = saved.phone;
                    if (saved.name) name = saved.name;
                }
            }
            userInfo = { phone: phone || 'Connected', name: name || 'KK Security Operator' };
            saveSavedUserInfo(userInfo);
        });

        client.on('authenticated', () => {
            console.log('🔒 [WhatsApp Service] WhatsApp Client Authenticated.');
            isConnected = true;
            isInitializing = false;
            qrCodeDataUrl = null;
        });

        client.on('auth_failure', (msg) => {
            console.error('❌ [WhatsApp Service] Authentication failed:', msg);
            isConnected = false;
            isInitializing = false;
            lastError = 'Auth failure: ' + msg;
        });

        client.on('disconnected', async (reason) => {
            console.warn('⚠️ [WhatsApp Service] WhatsApp was disconnected:', reason);
            isConnected = false;
            isInitializing = false;
            qrCodeDataUrl = null;
            await safeDestroyClient();
            setTimeout(() => {
                initWhatsApp(false);
            }, 5000);
        });

        await client.initialize();
    } catch (e) {
        console.error('❌ [WhatsApp Service] Setup exception:', e.message);
        isInitializing = false;
        lastError = e.message;
        cleanChromeLocks();
    }
}

// -------------------------------------------------------------
// HTTP ENDPOINTS
// -------------------------------------------------------------

app.get(['/', '/status'], (req, res) => {
    res.redirect('/api/whatsapp/status');
});

app.get('/api/whatsapp/dismissModal', async (req, res) => {
    try {
        if (!client || !client.pupPage) return res.json({ error: 'no pupPage' });
        const dismissed = await client.pupPage.evaluate(() => {
            const btns = Array.from(document.querySelectorAll('button, div[role="button"]'));
            const continueBtn = btns.find(b => b.innerText && (b.innerText.includes('Continue') || b.innerText.includes('OK') || b.innerText.includes('Got it')));
            if (continueBtn) {
                continueBtn.click();
                return { clicked: true, text: continueBtn.innerText };
            }
            return { clicked: false };
        });
        res.json(dismissed);
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.get('/api/whatsapp/debugContext', async (req, res) => {
    try {
        if (!client || !client.pupPage) {
            return res.json({ error: 'No client or pupPage' });
        }
        const p = client.pupPage;
        const mainF = p.mainFrame();
        const mainRealm = mainF.mainRealm();
        const resObj = {
            pageClosed: p.isClosed(),
            pageUrl: p.url(),
            mainFrameDetached: mainF.detached,
            mainRealmDisposed: mainRealm.disposed,
            hasContext: mainRealm.hasContext(),
            contextVal: !!mainRealm.context,
            clientInMainF: !!mainF._client(),
        };
        try {
            resObj.evalTest = await p.evaluate(() => 1 + 1);
        } catch (e) {
            resObj.evalError = e.message;
        }
        res.json(resObj);
    } catch (e) {
        res.status(500).json({ error: e.message, stack: e.stack });
    }
});

app.get('/api/whatsapp/debugFrames', async (req, res) => {
    try {
        if (!client || !client.pupBrowser) {
            return res.json({ error: 'No client or pupBrowser' });
        }
        const pages = await client.pupBrowser.pages();
        const info = pages.map((p, idx) => ({
            index: idx,
            url: p.url(),
            isClosed: p.isClosed(),
            frames: p.frames().map(f => ({
                url: f.url(),
                detached: f.detached,
                name: f.name()
            }))
        }));
        res.json({ pageCount: pages.length, pages: info });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.get('/api/whatsapp/status', (req, res) => {
    if (!client && !isInitializing) {
        initWhatsApp(false);
    }

    res.json({
        connected: isConnected,
        qr: qrCodeDataUrl,
        pairingCode: lastPairingCode,
        user: userInfo || (isConnected ? getSavedUserInfo() : null),
        hasSavedSession: fs.existsSync(AUTH_DIR),
        status: isConnected ? 'connected' : (qrCodeDataUrl ? 'qr_ready' : (isInitializing ? 'initializing' : 'disconnected')),
        error: lastError,
        message: isConnected ? 'WhatsApp Bot Authenticated & Ready' : (qrCodeDataUrl ? 'Scan QR Code with your phone' : 'Engine initializing...')
    });
});

app.post(['/api/whatsapp/qr-mode', '/api/whatsapp/reload-qr'], (req, res) => {
    if (isConnected) {
        return res.json({ success: true, connected: true, message: 'Already connected to WhatsApp.' });
    }
    initWhatsApp(false);
    res.json({ success: true, message: 'Refreshing QR code...' });
});

app.post('/api/whatsapp/pairing-code', async (req, res) => {
    const rawPhone = (req.body && req.body.phone) || '';
    const cleanPhone = String(rawPhone).replace(/\D/g, '');
    if (!cleanPhone) {
        return res.status(400).json({ success: false, error: 'Phone number is required.' });
    }

    if (isConnected) {
        return res.json({ success: true, connected: true, message: 'Already connected!', user: userInfo });
    }

    try {
        if (!client) {
            await initWhatsApp(false);
        }
        if (client && typeof client.requestPairingCode === 'function') {
            const code = await client.requestPairingCode(cleanPhone);
            lastPairingCode = code;
            return res.json({ success: true, pairingCode: code });
        } else {
            return res.status(500).json({ success: false, error: 'Pairing code not supported. Use QR Scan.' });
        }
    } catch (err) {
        console.error('Pairing code error:', err);
        return res.status(500).json({ success: false, error: err.message });
    }
});

async function safeClientSendMessage(chatId, content, options) {
    try {
        if (client.pupPage) {
            await client.pupPage.evaluate(() => {
                const btns = Array.from(document.querySelectorAll('button, div[role="button"]'));
                for (const b of btns) {
                    const txt = (b.innerText || '').trim();
                    if (txt === 'Continue' || txt === 'OK' || txt === 'Got it' || txt === 'Done') {
                        b.click();
                    }
                }
            }).catch(() => {});
        }
        return await client.sendMessage(chatId, content, options);
    } catch (err) {
        if (err && err.message && err.message.includes('detached frame')) {
            console.log('[WhatsApp Service] Detected detached frame during sendMessage; searching active page frames...');
            if (client.pupBrowser) {
                const pages = await client.pupBrowser.pages();
                for (const p of pages) {
                    if (p.url().includes('web.whatsapp.com')) {
                        client.pupPage = p;
                        break;
                    }
                }
            }
            return await client.sendMessage(chatId, content, options);
        }
        throw err;
    }
}

app.post(['/api/whatsapp/sendMessage', '/api/whatsapp/sendTest'], async (req, res) => {
    if (!isConnected || !client) {
        return res.status(503).json({ success: false, error: 'WhatsApp is not connected. Scan QR code first.' });
    }

    const { phone, message } = req.body || {};
    if (!phone || !message) {
        return res.status(400).json({ success: false, error: 'Phone and message are required.' });
    }

    let clean = String(phone).replace(/\D/g, '');
    if (clean.length === 10) clean = '91' + clean;
    const chatId = `${clean}@c.us`;

    try {
        await safeClientSendMessage(chatId, message);
        console.log(`[WhatsApp Service] Message delivered to ${chatId}`);
        res.json({ success: true, message: `Delivered message to +${clean}` });
    } catch (err) {
        console.error(`[WhatsApp Service] Failed to send message to ${chatId}:`, err);
        res.status(500).json({ success: false, error: err.message });
    }
});

app.post('/api/whatsapp/sendPhoto', upload.single('file'), async (req, res) => {
    if (!isConnected || !client) {
        if (req.file && fs.existsSync(req.file.path)) fs.unlinkSync(req.file.path);
        return res.status(503).json({ success: false, error: 'WhatsApp is not connected.' });
    }

    const phone = req.body.phone;
    const caption = req.body.caption || '';
    let clean = String(phone).replace(/\D/g, '');
    if (clean.length === 10) clean = '91' + clean;
    const chatId = `${clean}@c.us`;

    try {
        if (!req.file || !fs.existsSync(req.file.path)) {
            return res.status(400).json({ success: false, error: 'Photo file is missing.' });
        }

        const media = MessageMedia.fromFilePath(req.file.path);
        await safeClientSendMessage(chatId, media, { caption: caption });
        fs.unlinkSync(req.file.path);
        console.log(`[WhatsApp Service] Photo sent to ${chatId}`);
        res.json({ success: true, message: `Photo sent to +${clean}` });
    } catch (err) {
        if (req.file && fs.existsSync(req.file.path)) fs.unlinkSync(req.file.path);
        console.error('[WhatsApp Service] Send photo error:', err);
        res.status(500).json({ success: false, error: err.message });
    }
});

app.post('/api/whatsapp/broadcastThreatAlert', async (req, res) => {
    if (!isConnected || !client) {
        return res.status(503).json({ success: false, error: 'WhatsApp is not connected.' });
    }

    const phones = req.body.phones || [];
    const message = req.body.message || '';
    const combinedCardB64 = req.body.combined_card_base64 || '';

    if (!phones || phones.length === 0) {
        return res.status(400).json({ success: false, error: 'No phone numbers provided.' });
    }

    let media = null;
    if (combinedCardB64) {
        try {
            const cleanB64 = combinedCardB64.includes('base64,') ? combinedCardB64.split('base64,')[1] : combinedCardB64;
            media = new MessageMedia('image/jpeg', cleanB64, 'threat_evidence_board.jpg');
        } catch (e) {
            console.warn('[WhatsApp Service] Failed to parse card base64:', e.message);
        }
    }

    let sentCount = 0;
    for (const ph of phones) {
        let clean = String(ph).replace(/\D/g, '');
        if (clean.length === 10) clean = '91' + clean;
        const chatId = `${clean}@c.us`;
        try {
            if (media) {
                await safeClientSendMessage(chatId, media, { caption: message });
            } else {
                await safeClientSendMessage(chatId, message);
            }
            sentCount++;
            console.log(`[WhatsApp Service] Broadcasted alert to +${clean}`);
        } catch (e) {
            console.error(`[WhatsApp Service] Broadcast failure to +${clean}:`, e.message);
        }
    }

    res.json({ success: true, sentCount: sentCount, total: phones.length });
});

app.post(['/api/whatsapp/reset', '/api/whatsapp/unlink', '/api/whatsapp/logout'], async (req, res) => {
    console.log('[WhatsApp Service] Unlink / Reset requested by user.');
    await initWhatsApp(true);
    res.json({ success: true, message: 'WhatsApp unlinked. Generating fresh QR code for pairing.' });
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`===============================================`);
    console.log(`⚡ KK Security WhatsApp QR Microservice Running`);
    console.log(`🌐 Endpoint: http://127.0.0.1:${PORT}`);
    console.log(`📲 Status:   http://127.0.0.1:${PORT}/api/whatsapp/status`);
    console.log(`===============================================`);

    initWhatsApp(false);
});
