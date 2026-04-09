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

    // Request Camera
    navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        .then(stream => {
            video.srcObject = stream;
            video.play();

            // Capture frames every 5 seconds and send to backend for analysis.
            setInterval(() => {
                if (video.readyState === video.HAVE_ENOUGH_DATA) {
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

                    const base64Image = canvas.toDataURL('image/jpeg', 0.7);

                    ApiClient.post('/student/proctor_log', {
                        attempt_id: attemptId,
                        image: base64Image,
                        type: 'face_check'
                    }).then(res => {
                        if (res.ok) {
                            if (res.data.status === 'warning') {
                                consecutiveWarnings++;
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
            console.error("Camera error:", err);
            proctorStatus.className = 'badge bg-warning w-100 py-2 fs-6';
            proctorStatus.textContent = 'Camera unavailable';
        });

    // Tab Switch Detection
    // We log the event silently and show a non-blocking badge instead of an alert.
    // An alert() would itself trigger a visibilitychange and create a loop.
    let tabSwitchCount = 0;
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            tabSwitchCount++;
            ApiClient.post('/student/proctor_log', {
                attempt_id: attemptId,
                type: 'tab_switch'
            }).catch(() => {});
        } else {
            // Student returned to the exam tab
            if (tabSwitchCount > 0) {
                setStatusWarning(`Tab switch detected (${tabSwitchCount}x) — this is recorded.`);
            }
        }
    });
};
