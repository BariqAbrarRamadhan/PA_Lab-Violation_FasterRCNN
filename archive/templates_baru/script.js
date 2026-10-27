// Upload Video Page
const videoUpload = document.getElementById('video-upload');
const uploadBtn = document.getElementById('upload-btn');
const fileInfo = document.getElementById('file-info');
const fileName = document.getElementById('file-name');
const removeBtn = document.getElementById('remove-btn');

if (videoUpload) {
    videoUpload.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            fileName.textContent = file.name;
            fileInfo.style.display = 'flex';
            uploadBtn.disabled = false;
        }
    });
}

if (removeBtn) {
    removeBtn.addEventListener('click', () => {
        videoUpload.value = '';
        fileInfo.style.display = 'none';
        uploadBtn.disabled = true;
    });
}

if (uploadBtn) {
    uploadBtn.addEventListener('click', () => {
        alert('Upload functionality will be implemented here!');
        // Add your upload logic here
    });
}

// Upload URL Page
const videoUrl = document.getElementById('video-url');
const pasteBtn = document.getElementById('paste-btn');
const submitUrlBtn = document.getElementById('submit-url-btn');

if (pasteBtn) {
    pasteBtn.addEventListener('click', async () => {
        try {
            const text = await navigator.clipboard.readText();
            videoUrl.value = text;
        } catch (err) {
            console.error('Failed to read clipboard:', err);
        }
    });
}

if (submitUrlBtn) {
    submitUrlBtn.addEventListener('click', () => {
        const url = videoUrl.value.trim();
        if (url) {
            alert(`URL submitted: ${url}`);
            // Add your URL processing logic here
        } else {
            alert('Please enter a valid URL');
        }
    });
}

// Drag and drop functionality for upload area
const uploadArea = document.querySelector('.upload-area');

if (uploadArea) {
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = 'var(--primary-color)';
        uploadArea.style.background = 'var(--primary-light)';
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.style.borderColor = 'var(--border-color)';
        uploadArea.style.background = 'var(--background)';
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = 'var(--border-color)';
        uploadArea.style.background = 'var(--background)';

        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type.startsWith('video/')) {
            videoUpload.files = files;
            fileName.textContent = files[0].name;
            fileInfo.style.display = 'flex';
            uploadBtn.disabled = false;
        }
    });
}
