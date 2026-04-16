// Lightbox functionality for report images
(function() {
    'use strict';
    
    // Create modal elements on page load
    document.addEventListener('DOMContentLoaded', function() {
        // Create modal HTML
        const modalHTML = `
            <div id="lightbox-modal" class="lightbox-modal">
                <span class="lightbox-close">&times;</span>
                <div class="lightbox-content">
                    <img id="lightbox-img" src="" alt="">
                    <div class="lightbox-caption"></div>
                    <button class="lightbox-prev">&#10094;</button>
                    <button class="lightbox-next">&#10095;</button>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        
        // Get modal elements
        const modal = document.getElementById('lightbox-modal');
        const modalImg = document.getElementById('lightbox-img');
        const captionText = document.querySelector('.lightbox-caption');
        const closeBtn = document.querySelector('.lightbox-close');
        const prevBtn = document.querySelector('.lightbox-prev');
        const nextBtn = document.querySelector('.lightbox-next');
        
        // Get all figure cards
        const figures = Array.from(document.querySelectorAll('.figure-card img'));
        let currentIndex = 0;
        
        // Function to show image in lightbox
        function showImage(index) {
            if (index < 0 || index >= figures.length) return;
            currentIndex = index;
            
            const img = figures[index];
            const fullPath = img.getAttribute('data-full-path') || img.src;
            const caption = img.alt;
            
            modalImg.src = fullPath;
            captionText.textContent = caption;
            modal.style.display = 'block';
            
            // Update navigation button visibility
            prevBtn.style.display = index > 0 ? 'block' : 'none';
            nextBtn.style.display = index < figures.length - 1 ? 'block' : 'none';
        }
        
        // Add click handlers to all images
        figures.forEach((img, index) => {
            img.style.cursor = 'pointer';
            img.addEventListener('click', () => showImage(index));
        });
        
        // Close modal
        function closeModal() {
            modal.style.display = 'none';
        }
        
        closeBtn.addEventListener('click', closeModal);
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeModal();
            }
        });
        
        // Navigation
        prevBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            showImage(currentIndex - 1);
        });
        
        nextBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            showImage(currentIndex + 1);
        });
        
        // Keyboard navigation
        document.addEventListener('keydown', function(e) {
            if (modal.style.display === 'block') {
                if (e.key === 'Escape') {
                    closeModal();
                } else if (e.key === 'ArrowLeft') {
                    showImage(currentIndex - 1);
                } else if (e.key === 'ArrowRight') {
                    showImage(currentIndex + 1);
                }
            }
        });
    });
})();
