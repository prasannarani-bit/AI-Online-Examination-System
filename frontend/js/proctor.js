window.initProctoring = function (attemptId) {
    const video = document.getElementById('proctorVideo');
    const canvas = document.getElementById('proctorCanvas');
    const proctorStatus = document.getElementById('proctorStatus');
    const ctx = canvas.getContext('2d');

    // Client-side grace counter:
    // The backend already requires 2 consecutive bad frames before flagging,
    // which is ~10s of sustained behaviour. No extra client-side delay needed.
    // We still track consecutive warnings to auto-clear the badge reliably.
    let consecutiveWarnings = 0;
    let clearBadgeTimer = null;

    function setStatusOk() {
        consecutiveWarnings = 0;
        proctorStatus.className = 'badge bg-success w-100 py-2 fs-6';
        proctorStatus.textContent = 'Status: Normal';
    }

    function setStatusWarning(reason) {
        proctorStatus.className = 'badge bg-danger w-100 py-2 fs-6';
        proctorStatus.textContent = '⚠ ' + reason;
        // Auto-clear after 20 s if behaviour returns to normal
        if (clearBadgeTimer) clearTimeout(clearBadgeTimer);
        clearBadgeTimer = setTimeout(setStatusOk, 20000);
    }

    // Fullscreen and Input Restrictions
    function enterFullscreen() {
        if (document.documentElement.requestFullscreen) {
            document.documentElement.requestFullscreen().catch(() => {});
        }
    }
    
    // Block context menu and copy-paste
    document.addEventListener('contextmenu', e => e.preventDefault());
    document.addEventListener('copy', e => e.preventDefault());
    document.addEventListener('cut', e => e.preventDefault());
    document.addEventListener('paste', e => e.preventDefault());

    // Request Camera and Microphone
    navigator.mediaDevices.getUserMedia({ video: true, audio: true })
        .then(stream => {
            video.srcObject = stream;
            video.play();
            enterFullscreen();

            // --- Sound Monitoring Logic ---
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const analyser = audioContext.createAnalyser();
            const microphone = audioContext.createMediaStreamSource(stream);
            microphone.connect(analyser);
            analyser.fftSize = 256;
            const bufferLength = analyser.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);

            let highVolumeDuration = 0;
            const VOLUME_THRESHOLD = 45; // Sensitivity threshold (out of 255)
            const DETECTION_INTERVAL = 500; // Check every 0.5s

            setInterval(() => {
                analyser.getByteFrequencyData(dataArray);
                let sum = 0;
                for (let i = 0; i < bufferLength; i++) {
                    sum += dataArray[i];
                }
                const averageVolume = sum / bufferLength;

                if (averageVolume > VOLUME_THRESHOLD) {
                    highVolumeDuration += DETECTION_INTERVAL;
                    if (highVolumeDuration >= 2000) { // Sustained noise for 2s
                        setStatusWarning("Noise Detected: Maintain Silence");
                        ApiClient.post('/student/proctor_log', {
                            attempt_id: attemptId,
                            type: 'audio_violation'
                        }).catch(() => {});
                        highVolumeDuration = 0; // Reset after logging to avoid spam
                    }
                } else {
                    highVolumeDuration = 0;
                }
            }, DETECTION_INTERVAL);

            // --- Video Frame Capture ---
            setInterval(() => {
                if (video.readyState === video.HAVE_ENOUGH_DATA) {
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

                    const base64Image = canvas.toDataURL('image/jpeg', 0.6);

                    ApiClient.post('/student/proctor_log', {
                        attempt_id: attemptId,
                        image: base64Image,
                        type: 'face_check'
                    }).then(res => {
                        if (res.ok) {
                            if (res.data.status === 'warning') {
                                setStatusWarning(res.data.reason);
                            } else {
                                setStatusOk();
                            }
                        }
                    }).catch(err => console.error('Proctor error:', err));
                }
            }, 5000);
        })
        .catch(err => {
            console.error("Media access denied:", err);
            alert("Camera and Microphone access are mandatory for this exam. Please enable them to proceed.");
            window.location.href = 'student_dashboard.html';
        });

    // --- Strict Navigation Lockdown ---
    let violationCount = 0;
    const MAX_VIOLATIONS = 3;
    let isLocked = false;

    function triggerLockout(reason) {
        if (isLocked) return;
        isLocked = true;
        violationCount++;

        const overlay = document.getElementById('lockoutOverlay');
        const timerEl = document.getElementById('lockoutTimer');
        const msgEl = document.getElementById('violationCountMsg');
        
        overlay.classList.remove('d-none');
        msgEl.textContent = `Violation ${violationCount} / ${MAX_VIOLATIONS}`;

        // Auto-submit on 3rd violation
        if (violationCount >= MAX_VIOLATIONS) {
            msgEl.textContent = "CRITICAL VIOLATION: Disqualifying exam...";
            setTimeout(() => {
                window.location.href = 'submit_exam_forced.html?id=' + attemptId; // To be handled by start_exam's submit logic
                // Or directly trigger existing submit function if available in scope
                if (window.forceSubmitExam) window.forceSubmitExam();
            }, 3000);
            return;
        }

        let timeLeft = 10;
        timerEl.textContent = timeLeft;

        const interval = setInterval(() => {
            timeLeft--;
            timerEl.textContent = timeLeft;
            if (timeLeft <= 0) {
                clearInterval(interval);
                overlay.classList.add('d-none');
                isLocked = false;
                enterFullscreen(); // Re-request fullscreen
            }
        }, 1000);

        // Remote log
        ApiClient.post('/student/proctor_log', {
            attempt_id: attemptId,
            type: reason
        }).catch(() => {});
    }

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            triggerLockout('tab_switch');
        }
    });

    window.addEventListener('blur', () => {
        // Blur triggers when the user clicks out of the browser window 
        // (to another app, desktop, or even a system notification)
        if (!isLocked) {
            triggerLockout('background_activity');
        }
    });

    document.addEventListener('fullscreenchange', () => {
        if (!document.fullscreenElement && !isLocked) {
            triggerLockout('fullscreen_exit');
        }
    });
};
