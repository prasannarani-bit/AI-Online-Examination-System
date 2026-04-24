// Proctoring and Timer Logic
document.addEventListener('DOMContentLoaded', () => {
    // 1. Timer Logic
    const timerDisplay = document.getElementById('timerDisplay');
    const timeLeftInput = document.getElementById('timeLeft');
    const examForm = document.getElementById('examForm');
    
    if (timerDisplay && timeLeftInput && examForm) {
        let timeLeft = parseInt(timeLeftInput.value, 10);
        
        const updateTimerDisplay = () => {
            const minutes = Math.floor(timeLeft / 60);
            const seconds = timeLeft % 60;
            timerDisplay.textContent = `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
            if(timeLeft < 60) {
                timerDisplay.classList.remove('text-primary');
                timerDisplay.classList.add('text-danger', 'animate-pulse');
            }
        };
        
        const timerInterval = setInterval(() => {
            if (timeLeft <= 0) {
                clearInterval(timerInterval);
                alert("Time's up! Submitting exam.");
                examForm.submit();
            } else {
                updateTimerDisplay();
                timeLeft--;
            }
        }, 1000);
    }

    // 2. AI Proctoring WebCam Capture
    const video = document.getElementById('proctorVideo');
    const canvas = document.getElementById('proctorCanvas');
    const proctorUrl = document.getElementById('proctoringUrl');
    const proctorStatus = document.getElementById('proctorStatus');
    const attemptId = document.getElementById('attemptId');
    
    if (video && canvas && proctorUrl && attemptId) {
        const attempt_id = attemptId.value;
        const ctx = canvas.getContext('2d');

        // The backend requires 2 consecutive bad frames before flagging a violation
        // (~10 seconds of sustained bad behaviour). No extra client-side delay needed.
        let clearBadgeTimer = null;

        function setStatusOk() {
            if (proctorStatus) {
                proctorStatus.className = 'badge bg-success w-100 py-2 fs-6';
                proctorStatus.textContent = 'Status: Normal';
            }
        }

        function setStatusWarning(reason) {
            if (proctorStatus) {
                proctorStatus.className = 'badge bg-danger w-100 py-2 fs-6';
                proctorStatus.textContent = '\u26a0 ' + reason;
            }
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
                        
                        fetch(proctorUrl.value, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                attempt_id: attempt_id,
                                image: base64Image,
                                type: 'face_check'
                            })
                        })
                        .then(r => r.json())
                        .then(data => {
                            if (data.status === 'warning') {
                                setStatusWarning(data.reason);
                            } else {
                                setStatusOk();
                            }
                        })
                        .catch(err => console.error('Proctor error:', err));
                    }
                }, 5000);
            })
            .catch(err => {
                console.error("Camera error:", err);
                if (proctorStatus) {
                    proctorStatus.className = 'badge bg-warning w-100 py-2 fs-6';
                    proctorStatus.textContent = 'Camera unavailable';
                }
            });
            
        // 3. Tab Switch Detection
        // Log event silently and show a non-blocking badge when the student returns.
        // Using alert() inside visibilitychange causes it to re-fire on dismiss → loop.
        let tabSwitchCount = 0;
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                tabSwitchCount++;
                fetch(proctorUrl.value, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        attempt_id: attempt_id,
                        type: 'tab_switch'
                    })
                }).catch(() => {});
            } else {
                // Student returned to the exam tab — show badge (non-blocking)
                if (tabSwitchCount > 0) {
                    setStatusWarning(`Tab switch detected (${tabSwitchCount}x) \u2014 this is recorded.`);
                }
            }
        });
    }
});
