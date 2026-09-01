document.addEventListener('DOMContentLoaded', () => {
    // Drag and Drop Upload Interactivity
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');

    if (dropzone && fileInput) {
        dropzone.addEventListener('click', () => fileInput.click());

        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });

        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                updateDropzoneText(e.dataTransfer.files[0].name);
            }
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                updateDropzoneText(fileInput.files[0].name);
            }
        });
    }

    function updateDropzoneText(filename) {
        const titleText = document.getElementById('dropzone-title');
        if (titleText) {
            titleText.textContent = `Selected: ${filename}`;
        }
    }

    // Health Check Trigger Button
    const checkButtons = document.querySelectorAll('.btn-check-health');
    checkButtons.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const locId = btn.dataset.locationId;
            btn.disabled = true;
            btn.textContent = 'Checking...';
            
            try {
                const response = await fetch(`/locations/${locId}/health`, { method: 'POST' });
                const res = await response.json();
                window.location.reload();
            } catch (err) {
                alert('Health check failed: ' + err);
            }
        });
    });
});
