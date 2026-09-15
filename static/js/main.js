/**
 * Care Connect - Frontend JavaScript Helpers
 */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Theme Toggle
    initThemeToggle();

    // Auto-dismiss flash alerts after 6 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            try {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            } catch (e) {
                // Element might already be dismissed
            }
        }, 6000);
    });

    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));

    // Initialize Hospital Analytics Chart if canvas exists
    initHospitalCharts();

    // Auto-inject CSRF tokens into POST forms
    initCSRFProtection();

    // Attach AI Triage form listener if on patient dashboard
    initAITriage();
});

/**
 * Injects CSRF token into all state-changing HTML forms dynamically
 */
function initCSRFProtection() {
    const metaCsrf = document.querySelector('meta[name="csrf-token"]');
    if (metaCsrf) {
        const token = metaCsrf.getAttribute('content');
        if (token) {
            document.querySelectorAll('form[method="POST"], form[method="post"]').forEach(form => {
                if (!form.querySelector('input[name="csrf_token"]')) {
                    const hiddenInput = document.createElement('input');
                    hiddenInput.type = 'hidden';
                    hiddenInput.name = 'csrf_token';
                    hiddenInput.value = token;
                    form.appendChild(hiddenInput);
                }
            });
        }
    }
}

/**
 * Initializes Light / Dark theme toggling with localStorage persistence
 */
function initThemeToggle() {
    const themeBtn = document.getElementById('themeToggleBtn');
    const themeIcon = document.getElementById('themeIcon');

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-bs-theme', theme);
        localStorage.setItem('careconnect_theme', theme);
        if (themeIcon) {
            if (theme === 'dark') {
                themeIcon.className = 'bi bi-sun-fill text-warning';
                if (themeBtn) themeBtn.setAttribute('aria-label', 'Switch to light theme');
            } else {
                themeIcon.className = 'bi bi-moon-stars text-slate';
                if (themeBtn) themeBtn.setAttribute('aria-label', 'Switch to dark theme');
            }
        }
        window.dispatchEvent(new CustomEvent('careconnectThemeChanged', { detail: { theme } }));
    }

    const savedTheme = localStorage.getItem('careconnect_theme') || 'light';
    applyTheme(savedTheme);

    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const active = document.documentElement.getAttribute('data-bs-theme') || 'light';
            const next = active === 'dark' ? 'light' : 'dark';
            applyTheme(next);
        });
    }
}

/**
 * Fills demo credentials on the login screen
 */
function fillLogin(identifier, password) {
    const idInput = document.getElementById('identifier');
    const passInput = document.getElementById('password');
    if (idInput && passInput) {
        idInput.value = identifier;
        passInput.value = password;
        idInput.focus();
    }
}

/**
 * Initializes Chart.js on the Hospital Dashboard using real database data
 */
function initHospitalCharts() {
    const dataElement = document.getElementById('hospitalAnalyticsData');
    if (!dataElement || typeof Chart === 'undefined') return;

    let analytics = null;
    try {
        analytics = JSON.parse(dataElement.textContent || '{}');
    } catch (e) {
        console.error('Failed to parse hospital analytics data:', e);
        return;
    }

    // 1. Doctor Specialization Distribution Chart
    const specialtyCanvas = document.getElementById('specialtyChart');
    if (specialtyCanvas && analytics.specialties) {
        const labels = analytics.specialties.labels || [];
        const counts = analytics.specialties.counts || [];

        if (labels.length > 0 && counts.some(c => c > 0)) {
            new Chart(specialtyCanvas, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Doctors per Department',
                        data: counts,
                        backgroundColor: [
                            'rgba(15, 118, 110, 0.75)',
                            'rgba(2, 132, 199, 0.75)',
                            'rgba(124, 58, 237, 0.75)',
                            'rgba(245, 158, 11, 0.75)',
                            'rgba(16, 185, 129, 0.75)',
                            'rgba(239, 68, 68, 0.75)'
                        ],
                        borderRadius: 6,
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: { precision: 0 },
                            grid: { color: document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(226, 232, 240, 0.6)' }
                        },
                        x: { grid: { display: false } }
                    }
                }
            });
        }
    }

    // 2. Doctor Availability Status Chart
    const availCanvas = document.getElementById('availabilityChart');
    if (availCanvas && analytics.availability) {
        const labels = analytics.availability.labels || [];
        const counts = analytics.availability.counts || [];

        if (counts.some(c => c > 0)) {
            new Chart(availCanvas, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: counts,
                        backgroundColor: [
                            'rgba(16, 185, 129, 0.85)',
                            'rgba(148, 163, 184, 0.6)'
                        ],
                        hoverOffset: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom' }
                    }
                }
            });
        }
    }
}

/**
 * Handles AI Triage symptom analysis on Patient Dashboard
 */
function initAITriage() {
    const triageBtn = document.getElementById('analyzeSymptomsBtn');
    const symptomsInput = document.getElementById('symptomsInput');
    const resultsContainer = document.getElementById('aiResultsContainer');

    if (!triageBtn || !symptomsInput || !resultsContainer) return;

    triageBtn.addEventListener('click', async () => {
        const symptoms = symptomsInput.value.trim();
        if (!symptoms) {
            alert('Please describe your symptoms before analyzing.');
            return;
        }

        triageBtn.disabled = true;
        triageBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Analyzing with AI...';

        try {
            const response = await fetch('/patient/ai-triage', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ symptoms })
            });

            const data = await response.json();
            if (data.status === 'success') {
                const analysis = data.analysis;
                const doctors = data.recommended_doctors;

                let doctorsHtml = '';
                if (doctors.length > 0) {
                    doctorsHtml = doctors.map(doc => `
                        <div class="col-md-6 mb-2">
                            <div class="p-3 border rounded bg-white">
                                <h6 class="mb-1 text-primary">${doc.name}</h6>
                                <p class="small text-muted mb-1">${doc.specialization} &bull; ${doc.hospital}</p>
                                <span class="badge bg-success-subtle text-success">${doc.timing}</span>
                                <span class="badge bg-light text-dark ms-1">$${doc.fee} fee</span>
                            </div>
                        </div>
                    `).join('');
                } else {
                    doctorsHtml = '<p class="text-muted small">No specialists currently listed for this specific department in demo database.</p>';
                }

                resultsContainer.innerHTML = `
                    <div class="alert alert-info border-0 shadow-sm mt-3">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <h6 class="mb-0 fw-bold"><i class="bi bi-robot me-2"></i>AI Assessment Recommendation</h6>
                            <span class="badge bg-primary">${analysis.urgency_level} Priority</span>
                        </div>
                        <p class="mb-2"><strong>Recommended Specialist:</strong> <span class="badge bg-dark">${analysis.recommended_specialty}</span> (Confidence: ${(analysis.confidence * 100).toFixed(0)}%)</p>
                        <p class="small text-muted mb-3">${analysis.summary}</p>
                        
                        <h6 class="fw-bold mt-3 mb-2 small text-uppercase text-secondary">Matching Available Specialists</h6>
                        <div class="row">
                            ${doctorsHtml}
                        </div>
                    </div>
                `;
            }
        } catch (err) {
            console.error(err);
            resultsContainer.innerHTML = `<div class="alert alert-danger mt-3">Error processing symptoms analysis. Please try again.</div>`;
        } finally {
            triageBtn.disabled = false;
            triageBtn.innerHTML = '<i class="bi bi-magic me-2"></i>Analyze with AI';
        }
    });
}
