document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('projectForm');
    const loadingDiv = document.getElementById('loading');
    const resultDiv = document.getElementById('result');
    const outputPre = document.querySelector('#output pre');
    const fileList = document.getElementById('fileList');
    const downloadLinks = document.getElementById('downloadLinks');
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = new FormData(form);
        
        // Show loading spinner and hide result
        loadingDiv.classList.remove('hidden');
        resultDiv.classList.add('hidden');

        try {
            const response = await fetch('/process', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const data = await response.json();
            
            // Display result
            outputPre.textContent = data.refined_output;
            
            // Clear and populate file list
            fileList.innerHTML = '';
            data.created_files.forEach(file => {
                const li = document.createElement('li');
                li.textContent = file.split('/').pop();
                fileList.appendChild(li);
            });
            
            // Clear and populate download links
            downloadLinks.innerHTML = '';
            data.created_files.forEach(file => {
                addDownloadLink(file);
            });
            addDownloadLink(data.log_file, 'Log File');
            
            // Show result and hide loading spinner
            resultDiv.classList.remove('hidden');
            loadingDiv.classList.add('hidden');

            // Activate the first tab
            activateTab(tabButtons[0]);
        } catch (error) {
            console.error('Error:', error);
            alert('An error occurred. Please try again.');
            loadingDiv.classList.add('hidden');
        }
    });

    function addDownloadLink(file, label) {
        const link = document.createElement('a');
        link.href = `/download/${encodeURIComponent(file)}`;
        link.textContent = label || file.split('/').pop();
        link.download = file.split('/').pop();
        downloadLinks.appendChild(link);
    }

    // Tab functionality
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            activateTab(button);
        });
    });

    function activateTab(button) {
        tabButtons.forEach(btn => btn.classList.remove('active'));
        tabContents.forEach(content => content.classList.remove('active'));

        button.classList.add('active');
        document.getElementById(button.dataset.tab).classList.add('active');
    }
});