/**
 * SmartQ - Staff Dashboard & Bilingual Speech Announcement Engine
 * Subject: Principles of Digital Systems and Design (PDSD)
 */

document.addEventListener('DOMContentLoaded', () => {
    // State variables
    let currentToken = null;
    let availableVoices = [];
    let teluguVoice = null;
    let englishVoice = null;
    let pollInterval = null;
    let isHelpSoundPlaying = false;

    // DOM Elements
    const heroTokenNo = document.getElementById('heroTokenNo');
    const heroCustomerName = document.getElementById('heroCustomerName');
    const heroLanguage = document.getElementById('heroLanguage');
    const heroPriority = document.getElementById('heroPriority');
    const servingStatusBadge = document.getElementById('servingStatusBadge');

    const btnCallNext = document.getElementById('btnCallNext');
    const btnRepeatCall = document.getElementById('btnRepeatCall');
    const btnCompleteService = document.getElementById('btnCompleteService');
    const btnSkipService = document.getElementById('btnSkipService');

    const statWaiting = document.getElementById('statWaiting');
    const statServing = document.getElementById('statServing');
    const statServingSub = document.getElementById('statServingSub');
    const statCompleted = document.getElementById('statCompleted');
    const statSkipped = document.getElementById('statSkipped');
    const statTotal = document.getElementById('statTotal');

    const waitingTableBody = document.getElementById('waitingTableBody');
    const waitingCountPill = document.getElementById('waitingCountPill');
    const eventsList = document.getElementById('eventsList');
    const selectPriorityPolicy = document.getElementById('selectPriorityPolicy');
    const voiceStatusNote = document.getElementById('voiceStatusNote');

    const helpAlertBanner = document.getElementById('helpAlertBanner');
    const helpTime = document.getElementById('helpTime');
    const btnAckHelp = document.getElementById('btnAckHelp');

    const qrModal = document.getElementById('qrModal');
    const btnShowQr = document.getElementById('btnShowQr');
    const btnCloseQr = document.getElementById('btnCloseQr');

    const formStaffToken = document.getElementById('formStaffToken');
    const staffIsPriority = document.getElementById('staffIsPriority');
    const staffPriorityReason = document.getElementById('staffPriorityReason');

    // -------------------------------------------------------------
    // Web Audio Synthesizer (Buzzer & Chime Beeps)
    // -------------------------------------------------------------
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

    function playBeep(frequency = 880, duration = 0.15, type = 'sine') {
        try {
            if (audioCtx.state === 'suspended') {
                audioCtx.resume();
            }
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();

            osc.type = type;
            osc.frequency.setValueAtTime(frequency, audioCtx.currentTime);

            gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + duration);

            osc.connect(gain);
            gain.connect(audioCtx.destination);

            osc.start();
            osc.stop(audioCtx.currentTime + duration);
        } catch (e) {
            console.warn("Web Audio not allowed before interaction:", e);
        }
    }

    function playCallChime() {
        // High-low two-tone doorbell chime
        playBeep(659.25, 0.25, 'sine'); // E5
        setTimeout(() => playBeep(523.25, 0.4, 'sine'), 250); // C5
    }

    function playHelpAlarm() {
        // Urgent alert siren pulses
        let count = 0;
        const interval = setInterval(() => {
            playBeep(987.77, 0.12, 'square'); // B5
            count++;
            if (count >= 4) clearInterval(interval);
        }, 150);
    }

    // -------------------------------------------------------------
    // Speech Synthesis Engine (English & Telugu)
    // -------------------------------------------------------------
    function initSpeechVoices() {
        if (!('speechSynthesis' in window)) {
            voiceStatusNote.innerText = "⚠️ Web Speech API not supported in this browser.";
            return;
        }

        const populateVoices = () => {
            availableVoices = window.speechSynthesis.getVoices();
            
            // Find Telugu voice
            teluguVoice = availableVoices.find(v => v.lang.includes('te') || v.lang.includes('TE') || v.name.toLowerCase().includes('telugu'));

            // Find Tamil voice
            tamilVoice = availableVoices.find(v => v.lang.includes('ta') || v.lang.includes('TA') || v.name.toLowerCase().includes('tamil'));
            
            // Find English (India preferred, then US/UK)
            englishVoice = availableVoices.find(v => v.lang === 'en-IN') ||
                           availableVoices.find(v => v.lang.startsWith('en')) ||
                           availableVoices[0];

            let langNotes = [];
            if (teluguVoice) langNotes.push(`Telugu: <strong>${teluguVoice.name}</strong>`);
            if (tamilVoice) langNotes.push(`Tamil: <strong>${tamilVoice.name}</strong>`);
            langNotes.push(`English: <strong>${englishVoice ? englishVoice.name : 'Default'}</strong>`);

            voiceStatusNote.innerHTML = `✓ Voice Engine Ready: ${langNotes.join(' | ')}`;
        };

        populateVoices();
        if (window.speechSynthesis.onvoiceschanged !== undefined) {
            window.speechSynthesis.onvoiceschanged = populateVoices;
        }
    }

    function speakAnnouncement(text, lang = 'en') {
        if (!('speechSynthesis' in window)) return;

        // Resume speech engine if paused
        if (window.speechSynthesis.paused) {
            window.speechSynthesis.resume();
        }
        window.speechSynthesis.cancel(); // Cancel any lingering speech

        // Play alert chime first
        playCallChime();

        setTimeout(() => {
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 0.9; // Slightly slower for clarity
            utterance.pitch = 1.0;
            utterance.volume = 1.0;

            if (lang === 'ta' && tamilVoice) {
                utterance.voice = tamilVoice;
                utterance.lang = tamilVoice.lang;
            } else if (lang === 'te' && teluguVoice) {
                utterance.voice = teluguVoice;
                utterance.lang = teluguVoice.lang;
            } else if (englishVoice) {
                utterance.voice = englishVoice;
                utterance.lang = englishVoice.lang || 'en-IN';
            }

            window.speechSynthesis.speak(utterance);
        }, 500);
    }

    // Voice test buttons
    document.getElementById('btnSpeakEn').addEventListener('click', () => {
        speakAnnouncement("Token number A 0 0 1, please proceed to Counter 1.", 'en');
    });

    document.getElementById('btnSpeakTe').addEventListener('click', () => {
        // If telugu voice available, speak Telugu Unicode, else phonetic transliteration
        if (teluguVoice) {
            speakAnnouncement("టోకెన్ సంఖ్య A 0 0 1, దయచేసి కౌంటర్ 1 వద్దకు రండి.", 'te');
        } else {
            speakAnnouncement("Token sankhya A 0 0 1, dayachesi Counter 1 vaddaku randi.", 'te');
        }
    });

    const btnSpeakTa = document.getElementById('btnSpeakTa');
    if (btnSpeakTa) {
        btnSpeakTa.addEventListener('click', () => {
            if (tamilVoice) {
                speakAnnouncement("டோக்கன் எண் A 0 0 1, தயவுசெய்து கவுண்டர் 1-க்கு வரவும்.", 'ta');
            } else {
                speakAnnouncement("Token en A 0 0 1, thayavuseithu Counter 1-kku varavum.", 'ta');
            }
        });
    }

    document.getElementById('btnTestVoice').addEventListener('click', () => {
        document.getElementById('btnSpeakEn').click();
    });

    // -------------------------------------------------------------
    // Dashboard Rendering
    // -------------------------------------------------------------
    function updateDashboardUI(data) {
        // Stats
        statWaiting.innerText = data.stats.waiting_count;
        statCompleted.innerText = data.stats.completed_today;
        statSkipped.innerText = data.stats.skipped_today;
        statTotal.innerText = data.stats.total_today;
        waitingCountPill.innerText = data.stats.waiting_count;

        // Current Serving Token
        currentToken = data.current_token;
        if (currentToken) {
            heroTokenNo.innerText = currentToken.token_no;
            heroCustomerName.innerText = currentToken.name || 'Walk-in Customer';
            heroLanguage.innerText = (currentToken.preferred_language || 'en').toUpperCase();
            
            if (currentToken.is_priority) {
                heroPriority.style.display = 'inline-flex';
                heroPriority.innerText = `★ PRIORITY (${currentToken.priority_reason || 'Special'})`;
            } else {
                heroPriority.style.display = 'none';
            }

            servingStatusBadge.innerText = 'SERVING NOW';
            servingStatusBadge.className = 'status-indicator live';

            statServing.innerText = currentToken.token_no;
            statServingSub.innerText = currentToken.name || 'Serving';

            btnRepeatCall.disabled = false;
            btnCompleteService.disabled = false;
            btnSkipService.disabled = false;

            // WhatsApp Turn Alert Status & Instant Resend
            const btnWhatsAppAlert = document.getElementById('btnWhatsAppAlert');
            if (btnWhatsAppAlert) {
                if (currentToken.phone) {
                    btnWhatsAppAlert.style.display = 'inline-flex';
                    btnWhatsAppAlert.innerHTML = `<span>💬</span> <span>Auto-Delivered (:3005)</span>`;
                    btnWhatsAppAlert.removeAttribute('href');
                    btnWhatsAppAlert.style.cursor = 'pointer';
                    btnWhatsAppAlert.title = 'Click to resend WhatsApp alert via local microservice';
                    btnWhatsAppAlert.onclick = () => window.sendDirectWhatsApp(currentToken.phone, currentToken.token_no, currentToken.name);
                } else {
                    btnWhatsAppAlert.style.display = 'none';
                }
            }
        } else {
            heroTokenNo.innerText = '---';
            heroCustomerName.innerText = 'No Active Token';
            heroLanguage.innerText = 'EN';
            heroPriority.style.display = 'none';

            servingStatusBadge.innerText = 'COUNTER READY';
            servingStatusBadge.className = 'status-indicator';

            statServing.innerText = '-';
            statServingSub.innerText = 'Counter Ready';

            btnRepeatCall.disabled = true;
            btnCompleteService.disabled = true;
            btnSkipService.disabled = true;

            const btnWhatsAppAlert = document.getElementById('btnWhatsAppAlert');
            if (btnWhatsAppAlert) btnWhatsAppAlert.style.display = 'none';
        }

        // Enable/Disable Call Next button based on waiting count
        btnCallNext.disabled = (data.stats.waiting_count === 0);

        // Render Waiting Table
        renderWaitingTable(data.waiting_list);

        // Priority Mode Setting
        if (selectPriorityPolicy.value !== data.settings.priority_mode) {
            selectPriorityPolicy.value = data.settings.priority_mode;
        }

        // Help Alert handling
        if (data.settings.help_active) {
            helpAlertBanner.style.display = 'flex';
            helpTime.innerText = data.settings.help_time || 'Just now';
            if (!isHelpSoundPlaying) {
                playHelpAlarm();
                isHelpSoundPlaying = true;
            }
        } else {
            helpAlertBanner.style.display = 'none';
            isHelpSoundPlaying = false;
        }
    }

    function renderWaitingTable(list) {
        if (!list || list.length === 0) {
            waitingTableBody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center empty-state">No customers waiting in queue.</td>
                </tr>
            `;
            return;
        }

        let html = '';
        list.forEach((t, idx) => {
            const isPriority = t.is_priority === 1;
            const priorityBadge = isPriority 
                ? `<span class="badge badge-priority" title="${t.priority_reason || 'Priority'}">★ PRIORITY</span>` 
                : `<span class="text-muted">Normal</span>`;
            
            const sourceBadge = `<span class="badge">${t.source.toUpperCase()}</span>`;
            const langBadge = `<span class="badge badge-lang">${(t.preferred_language || 'en').toUpperCase()}</span>`;

            const waBtn = t.phone 
                ? `<button type="button" onclick="window.sendDirectWhatsApp('${t.phone}', '${t.token_no}', '${t.name || 'Patient'}')" class="btn btn-xs" style="background:rgba(37,211,102,0.15); border:1px solid #25D366; color:#25D366; font-weight:700; padding:0.25rem 0.5rem; cursor:pointer;" title="Send instant WhatsApp message via local microservice (:3005)">💬 Auto</button>`
                : '';

            html += `
                <tr>
                    <td><strong>${idx + 1}</strong></td>
                    <td class="token-cell">${t.token_no}</td>
                    <td>
                        <div>${t.name || '<span class="text-muted">Walk-in</span>'}</div>
                        ${t.phone ? `<div style="font-size:0.75rem; color:#94a3b8; font-family:var(--font-mono);">${t.phone}</div>` : ''}
                    </td>
                    <td>${langBadge}</td>
                    <td>${sourceBadge}</td>
                    <td>
                        <button class="btn btn-xs ${isPriority ? 'btn-warning' : 'btn-outline'}" 
                                onclick="window.toggleTokenPriority(${t.id}, ${!isPriority})" 
                                title="Click to toggle priority status">
                            ${priorityBadge}
                        </button>
                    </td>
                    <td>
                        <div style="display:flex; gap:4px;">
                            ${waBtn}
                            <a href="/ticket/${t.token_no}" target="_blank" class="btn btn-xs btn-outline" title="Print ticket">
                                🖨️
                            </a>
                        </div>
                    </td>
                </tr>
            `;
        });
        waitingTableBody.innerHTML = html;
    }

    async function fetchQueueData() {
        try {
            const res = await fetch('/api/queue');
            const data = await res.json();
            if (data.success) {
                updateDashboardUI(data);
            }
        } catch (err) {
            console.error("Queue fetch error:", err);
        }
    }

    async function fetchAuditEvents() {
        try {
            const res = await fetch('/api/events');
            const data = await res.json();
            if (data.success && data.events.length > 0) {
                let html = '';
                data.events.slice(0, 15).forEach(e => {
                    const timeOnly = e.created_at.split(' ')[1] || e.created_at;
                    html += `
                        <li class="event-item">
                            <span>${e.message}</span>
                            <span class="event-time">${timeOnly}</span>
                        </li>
                    `;
                });
                eventsList.innerHTML = html;
            }
        } catch (err) {
            console.error("Events fetch error:", err);
        }
    }

    // -------------------------------------------------------------
    // Action Button Handlers
    // -------------------------------------------------------------

    // Call Next
    btnCallNext.addEventListener('click', async () => {
        btnCallNext.disabled = true;
        try {
            const res = await fetch('/api/queue/call-next', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ auto_complete_previous: true })
            });
            const data = await res.json();
            if (data.success) {
                const lang = data.preferred_language || 'en';
                const announcementText = data.announcement[lang] || data.announcement['en'];
                speakAnnouncement(announcementText, lang);
                fetchQueueData();
                fetchAuditEvents();
            } else {
                alert(data.message || 'No token to call.');
            }
        } catch (err) {
            console.error(err);
            alert('Error calling next token.');
        } finally {
            setTimeout(() => { btnCallNext.disabled = false; }, 800);
        }
    });

    // Repeat Call
    btnRepeatCall.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/queue/repeat', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                const lang = data.preferred_language || 'en';
                const announcementText = data.announcement[lang] || data.announcement['en'];
                speakAnnouncement(announcementText, lang);
                fetchAuditEvents();
            }
        } catch (err) {
            console.error(err);
        }
    });

    // Complete Service - Open Digital Prescription Modal
    const prescriptionModal = document.getElementById('prescriptionModal');
    const rxModalToken = document.getElementById('rxModalToken');
    const rxModalPatient = document.getElementById('rxModalPatient');
    const btnConfirmCompleteRx = document.getElementById('btnConfirmCompleteRx');
    const btnCancelRxModal = document.getElementById('btnCancelRxModal');
    const btnCloseRxModal = document.getElementById('btnCloseRxModal');

    btnCompleteService.addEventListener('click', () => {
        if (!currentToken) return;
        if (rxModalToken) rxModalToken.innerText = currentToken.token_no;
        if (rxModalPatient) rxModalPatient.innerText = currentToken.name || 'Walk-in Patient';
        if (prescriptionModal) prescriptionModal.style.display = 'flex';
    });

    if (btnCloseRxModal) btnCloseRxModal.addEventListener('click', () => { prescriptionModal.style.display = 'none'; });
    if (btnCancelRxModal) btnCancelRxModal.addEventListener('click', () => { prescriptionModal.style.display = 'none'; });

    if (btnConfirmCompleteRx) {
        btnConfirmCompleteRx.addEventListener('click', async () => {
            btnConfirmCompleteRx.disabled = true;
            btnConfirmCompleteRx.innerText = 'Completing & Sending...';

            const diagnosis = document.getElementById('rxDiagnosisInput').value.trim();
            const doctor_notes = document.getElementById('rxDoctorNotesInput').value.trim();

            // Extract medicines from inputs
            const medItems = [];
            document.querySelectorAll('#rxMedicinesList .rx-med-item').forEach(item => {
                const name = item.querySelector('.rx-name').value.trim();
                const dosage = item.querySelector('.rx-dose').value.trim();
                const duration = item.querySelector('.rx-dur').value.trim();
                if (name) {
                    medItems.push({ name, dosage, frequency: dosage, duration, notes: 'As directed' });
                }
            });

            try {
                const res = await fetch('/api/queue/complete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        token_id: currentToken ? currentToken.id : null,
                        diagnosis: diagnosis,
                        doctor_notes: doctor_notes,
                        prescription: medItems
                    })
                });
                const data = await res.json();
                if (data.success) {
                    prescriptionModal.style.display = 'none';
                    playBeep(523.25, 0.15);
                    fetchQueueData();
                    fetchAuditEvents();
                    fetchWhatsAppOutbox();
                } else {
                    alert(data.message || 'Error completing token.');
                }
            } catch (err) {
                console.error(err);
                alert('Network error.');
            } finally {
                btnConfirmCompleteRx.disabled = false;
                btnConfirmCompleteRx.innerText = '✓ Complete & Send Prescription';
            }
        });
    }

    // Skip Service
    btnSkipService.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to skip this customer?')) return;
        try {
            const res = await fetch('/api/queue/skip', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                fetchQueueData();
                fetchAuditEvents();
            }
        } catch (err) {
            console.error(err);
        }
    });

    // Priority Policy Change
    selectPriorityPolicy.addEventListener('change', async () => {
        const mode = selectPriorityPolicy.value;
        try {
            await fetch('/api/settings/priority-mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode })
            });
            fetchQueueData();
        } catch (err) {
            console.error(err);
        }
    });

    // Window global method for table toggle
    window.toggleTokenPriority = async function(tokenId, newPriority) {
        try {
            await fetch(`/api/tokens/${tokenId}/priority`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_priority: newPriority })
            });
            fetchQueueData();
            fetchAuditEvents();
        } catch (err) {
            console.error(err);
        }
    };

    // Acknowledge Help Alert
    btnAckHelp.addEventListener('click', async () => {
        try {
            await fetch('/api/device/help/ack', { method: 'POST' });
            helpAlertBanner.style.display = 'none';
            isHelpSoundPlaying = false;
            fetchQueueData();
            fetchAuditEvents();
        } catch (err) {
            console.error(err);
        }
    });

    // Staff Token Form
    staffIsPriority.addEventListener('change', () => {
        staffPriorityReason.style.display = staffIsPriority.checked ? 'block' : 'none';
    });

    formStaffToken.addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            name: document.getElementById('staffCustName').value.trim(),
            phone: document.getElementById('staffCustPhone').value.trim(),
            preferred_language: document.getElementById('staffCustLang').value,
            is_priority: staffIsPriority.checked,
            priority_reason: staffIsPriority.checked ? staffPriorityReason.value.trim() : ''
        };

        try {
            const res = await fetch('/api/tokens/staff', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.success) {
                formStaffToken.reset();
                staffPriorityReason.style.display = 'none';
                playBeep(880, 0.15);
                fetchQueueData();
                fetchAuditEvents();
                // Open printable ticket in new tab
                window.open(data.ticket_url + '?autoprint=1', '_blank');
            }
        } catch (err) {
            console.error(err);
            alert('Failed to generate staff token.');
        }
    });

    // Seed Demo Data (28 Patients)
    const btnSeedDemoData = document.getElementById('btnSeedDemoData');
    if (btnSeedDemoData) {
        btnSeedDemoData.addEventListener('click', async () => {
            if (!confirm('Populate 28 realistic clinic patient records into the queue and sync with Supabase?')) return;
            btnSeedDemoData.disabled = true;
            btnSeedDemoData.innerText = '⏳ Seeding 28 records...';
            try {
                const res = await fetch('/api/queue/seed-demo', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    fetchQueueData();
                    fetchAuditEvents();
                } else {
                    alert('Notice: ' + data.message);
                }
            } catch (err) {
                console.error(err);
                alert('Error seeding demo data');
            } finally {
                btnSeedDemoData.disabled = false;
                btnSeedDemoData.innerText = '🌱 Populate 28 Patients';
            }
        });
    }

    // Reset Queue
    document.getElementById('btnResetQueue').addEventListener('click', async () => {
        if (!confirm('This will complete all active tokens and reset the sequence to 1. Continue?')) return;
        try {
            await fetch('/api/queue/reset', { method: 'POST' });
            fetchQueueData();
            fetchAuditEvents();
        } catch (err) {
            console.error(err);
        }
    });

    // Refresh button
    document.getElementById('btnRefreshQueue').addEventListener('click', () => {
        fetchQueueData();
        fetchAuditEvents();
    });

    // QR Modals
    btnShowQr.addEventListener('click', () => { qrModal.style.display = 'flex'; });
    btnCloseQr.addEventListener('click', () => { qrModal.style.display = 'none'; });
    qrModal.addEventListener('click', (e) => {
        if (e.target === qrModal) qrModal.style.display = 'none';
    });

    const btnShowEntranceQr = document.getElementById('btnShowEntranceQr');
    const entranceQrModal = document.getElementById('entranceQrModal');
    const btnCloseEntranceQr = document.getElementById('btnCloseEntranceQr');

    if (btnShowEntranceQr && entranceQrModal) {
        btnShowEntranceQr.addEventListener('click', () => { entranceQrModal.style.display = 'flex'; });
    }
    if (btnCloseEntranceQr && entranceQrModal) {
        btnCloseEntranceQr.addEventListener('click', () => { entranceQrModal.style.display = 'none'; });
    }
    if (entranceQrModal) {
        entranceQrModal.addEventListener('click', (e) => {
            if (e.target === entranceQrModal) entranceQrModal.style.display = 'none';
        });
    }

    // -------------------------------------------------------------
    // Initialization & Polling
    // -------------------------------------------------------------
    async function fetchWhatsAppOutbox() {
        try {
            const res = await fetch('/api/whatsapp/outbox');
            const data = await res.json();
            const outboxList = document.getElementById('whatsappOutboxList');
            const waCountPill = document.getElementById('waCountPill');

            if (data.success && data.outbox) {
                if (waCountPill) waCountPill.innerText = data.outbox.length;
                if (!outboxList) return;

                if (data.outbox.length === 0) {
                    outboxList.innerHTML = `<li class="event-item text-muted">No WhatsApp messages dispatched yet.</li>`;
                    return;
                }

                let html = '';
                data.outbox.slice(0, 10).forEach(m => {
                    const timeOnly = m.created_at.split(' ')[1] || m.created_at;
                    const directBtn = m.phone 
                        ? `<button type="button" onclick="window.sendDirectWhatsApp('${m.phone}', '${m.token_no || ''}', '${m.patient_name || 'Patient'}')" style="background:transparent; border:none; color:#25D366; cursor:pointer; font-weight:700; margin-left:6px; font-size:0.75rem;" title="Resend via microservice (:3005)">⚡ Auto-Resend</button>`
                        : '';
                    html += `
                        <li class="event-item" style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <strong style="color:#38bdf8;">${m.token_no || 'Tkn'}</strong>: ${m.patient_name || 'Patient'}
                                <div style="font-size:0.7rem; color:#94a3b8;">${m.event_type} | <span style="color:#34d399;">${m.status}</span> ${directBtn}</div>
                            </div>
                            <span class="event-time">${timeOnly}</span>
                        </li>
                    `;
                });
                outboxList.innerHTML = html;
            }
        } catch (err) {
            console.error("WhatsApp outbox fetch error:", err);
        }
    }

    window.sendDirectWhatsApp = async function(phone, tokenNo, name) {
        if (!phone) {
            alert('No phone number available.');
            return;
        }
        try {
            const res = await fetch('/api/whatsapp/send-direct', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone: phone, token_no: tokenNo, name: name })
            });
            const data = await res.json();
            if (data.success) {
                alert(`✓ Automated WhatsApp message sent to +91${phone} via Microservice (:3005)!`);
                fetchWhatsAppOutbox();
            } else {
                alert('Notice: ' + data.message);
            }
        } catch (err) {
            console.error('Send direct WhatsApp error:', err);
            alert('Network error sending WhatsApp message.');
        }
    };

    const btnRefreshWhatsApp = document.getElementById('btnRefreshWhatsApp');
    if (btnRefreshWhatsApp) {
        btnRefreshWhatsApp.addEventListener('click', () => {
            fetchWhatsAppOutbox();
        });
    }

    // Supabase Cloud Modal Logic
    const btnSupabaseCloud = document.getElementById('btnSupabaseCloud');
    const supabaseModal = document.getElementById('supabaseModal');
    const btnCloseSupabase = document.getElementById('btnCloseSupabase');
    const sbStatusBadge = document.getElementById('sbStatusBadge');
    const sbTablesNotice = document.getElementById('sbTablesNotice');
    const btnSyncSupabaseNow = document.getElementById('btnSyncSupabaseNow');
    const btnCopySbSchema = document.getElementById('btnCopySbSchema');
    const sbSchemaText = document.getElementById('sbSchemaText');

    async function checkSupabaseStatus() {
        try {
            const res = await fetch('/api/supabase/status');
            const data = await res.json();
            if (data.connected) {
                if (data.tables_ready) {
                    sbStatusBadge.innerText = '● Connected & Tables Ready';
                    sbStatusBadge.style.color = '#3ECF8E';
                    sbStatusBadge.style.borderColor = '#3ECF8E';
                    sbTablesNotice.innerHTML = `✅ All 5 tables are active in Supabase Cloud: <code>${data.existing_tables.join(', ')}</code>`;
                } else {
                    sbStatusBadge.innerText = '● Connected (Tables Needed)';
                    sbStatusBadge.style.color = '#f59e0b';
                    sbStatusBadge.style.borderColor = '#f59e0b';
                    sbTablesNotice.innerHTML = `⚠️ Database connected! Missing tables: <code>${data.missing_tables.join(', ')}</code>.<br>Run the SQL script below in your Supabase SQL Editor.`;
                }
            } else {
                sbStatusBadge.innerText = '● Disconnected';
                sbStatusBadge.style.color = '#ef4444';
                sbStatusBadge.style.borderColor = '#ef4444';
                sbTablesNotice.innerText = data.error || 'Failed to connect to Supabase.';
            }
        } catch (err) {
            console.error('Supabase status error:', err);
        }
    }

    async function loadSupabaseSchema() {
        try {
            const res = await fetch('/api/supabase/schema');
            const data = await res.json();
            if (data.success && sbSchemaText) {
                sbSchemaText.value = data.schema;
            }
        } catch (err) {
            console.error('Supabase schema error:', err);
        }
    }

    if (btnSupabaseCloud && supabaseModal) {
        btnSupabaseCloud.addEventListener('click', () => {
            supabaseModal.style.display = 'flex';
            checkSupabaseStatus();
            loadSupabaseSchema();
        });
    }
    if (btnCloseSupabase && supabaseModal) {
        btnCloseSupabase.addEventListener('click', () => { supabaseModal.style.display = 'none'; });
    }
    if (supabaseModal) {
        supabaseModal.addEventListener('click', (e) => {
            if (e.target === supabaseModal) supabaseModal.style.display = 'none';
        });
    }

    if (btnSyncSupabaseNow) {
        btnSyncSupabaseNow.addEventListener('click', async () => {
            btnSyncSupabaseNow.disabled = true;
            btnSyncSupabaseNow.innerText = '⏳ Syncing Data...';
            try {
                const res = await fetch('/api/supabase/sync', { method: 'POST' });
                const data = await res.json();
                alert(data.message || 'Data synced to Supabase Cloud!');
                checkSupabaseStatus();
            } catch (err) {
                alert('Sync failed. Please ensure tables exist in Supabase.');
            } finally {
                btnSyncSupabaseNow.disabled = false;
                btnSyncSupabaseNow.innerText = '🚀 Sync All Data to Cloud';
            }
        });
    }

    if (btnCopySbSchema && sbSchemaText) {
        btnCopySbSchema.addEventListener('click', () => {
            navigator.clipboard.writeText(sbSchemaText.value);
            btnCopySbSchema.innerText = '✓ Copied!';
            setTimeout(() => { btnCopySbSchema.innerText = '📋 Copy SQL'; }, 2000);
        });
    }

    // WhatsApp Web Automated Sender Linking
    const btnLinkWhatsAppWeb = document.getElementById('btnLinkWhatsAppWeb');
    const whatsappWebModal = document.getElementById('whatsappWebModal');
    const btnCloseWhatsAppWeb = document.getElementById('btnCloseWhatsAppWeb');
    const waWebStatusBadge = document.getElementById('waWebStatusBadge');
    const waWebQrSection = document.getElementById('waWebQrSection');
    const waWebConnectedSection = document.getElementById('waWebConnectedSection');
    const waWebQrImg = document.getElementById('waWebQrImg');
    const btnRefreshWaWebQr = document.getElementById('btnRefreshWaWebQr');
    const waWebSentCount = document.getElementById('waWebSentCount');
    const waWebNavLabel = document.getElementById('waWebNavLabel');
    const btnSendWaTest = document.getElementById('btnSendWaTest');
    const waTestPhone = document.getElementById('waTestPhone');
    const waTestText = document.getElementById('waTestText');

    let waWebPollingInterval = null;

    async function checkWhatsAppWebStatus() {
        try {
            const res = await fetch('/api/whatsapp/web/status');
            const data = await res.json();

            if (data.connected) {
                if (waWebStatusBadge) {
                    waWebStatusBadge.innerText = '● Connected as Sender';
                    waWebStatusBadge.style.color = '#25D366';
                    waWebStatusBadge.style.borderColor = '#25D366';
                    waWebStatusBadge.style.background = 'rgba(37,211,102,0.15)';
                }
                if (waWebNavLabel) waWebNavLabel.innerText = '🟢 WhatsApp Linked';
                if (waWebQrSection) waWebQrSection.style.display = 'none';
                if (waWebConnectedSection) waWebConnectedSection.style.display = 'block';
                if (waWebSentCount) waWebSentCount.innerText = data.sent_count;
            } else {
                if (waWebStatusBadge) {
                    waWebStatusBadge.innerText = data.status === 'SCAN_QR' ? '🟡 Scan QR with WhatsApp' : 'Starting...';
                    waWebStatusBadge.style.color = '#fbbf24';
                    waWebStatusBadge.style.borderColor = '#f59e0b';
                }
                if (waWebNavLabel) waWebNavLabel.innerText = 'Link WhatsApp';
                if (waWebQrSection) waWebQrSection.style.display = 'block';
                if (waWebConnectedSection) waWebConnectedSection.style.display = 'none';
            }
        } catch (err) {
            console.error('WhatsApp Web status error:', err);
        }
    }

    function refreshWaWebQrImage() {
        if (waWebQrImg) {
            waWebQrImg.src = '/api/whatsapp/web/qr.png?t=' + Date.now();
        }
    }

    if (btnLinkWhatsAppWeb && whatsappWebModal) {
        btnLinkWhatsAppWeb.addEventListener('click', async () => {
            whatsappWebModal.style.display = 'flex';
            checkWhatsAppWebStatus();
            refreshWaWebQrImage();
            // Start worker if not started
            fetch('/api/whatsapp/web/start', { method: 'POST' });

            clearInterval(waWebPollingInterval);
            waWebPollingInterval = setInterval(() => {
                checkWhatsAppWebStatus();
                // refresh QR code every 10s if waiting
                refreshWaWebQrImage();
            }, 6000);
        });
    }

    if (btnCloseWhatsAppWeb && whatsappWebModal) {
        btnCloseWhatsAppWeb.addEventListener('click', () => {
            whatsappWebModal.style.display = 'none';
            clearInterval(waWebPollingInterval);
        });
    }

    if (whatsappWebModal) {
        whatsappWebModal.addEventListener('click', (e) => {
            if (e.target === whatsappWebModal) {
                whatsappWebModal.style.display = 'none';
                clearInterval(waWebPollingInterval);
            }
        });
    }

    if (btnRefreshWaWebQr) {
        btnRefreshWaWebQr.addEventListener('click', () => {
            refreshWaWebQrImage();
        });
    }

    if (btnSendWaTest) {
        btnSendWaTest.addEventListener('click', async () => {
            const phone = waTestPhone ? waTestPhone.value.trim() : '';
            const msg = waTestText ? waTestText.value.trim() : '';

            if (phone.length !== 10) {
                alert('Please enter a valid 10-digit phone number.');
                return;
            }

            btnSendWaTest.disabled = true;
            btnSendWaTest.innerText = 'Sending...';

            try {
                const res = await fetch('/api/whatsapp/web/send-test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone, message: msg })
                });
                const data = await res.json();
                if (data.success) {
                    alert('Message queued for instant delivery via WhatsApp Web!');
                } else {
                    alert('Failed to queue message.');
                }
            } catch (err) {
                alert('Request failed.');
            } finally {
                btnSendWaTest.disabled = false;
                btnSendWaTest.innerText = 'Send';
            }
        });
    }

    // Check status on startup
    checkWhatsAppWebStatus();

    initSpeechVoices();
    fetchQueueData();
    fetchAuditEvents();
    fetchWhatsAppOutbox();

    // Regular polling every 3 seconds for real-time responsiveness
    pollInterval = setInterval(() => {
        fetchQueueData();
        fetchAuditEvents();
        fetchWhatsAppOutbox();
    }, 3000);
});
