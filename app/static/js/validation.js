document.addEventListener('DOMContentLoaded', () => {
  const ticketForm = document.getElementById('ticketSubmissionForm');
  const submitBtn = document.getElementById('submitBtn');
  const btnText = document.getElementById('btnText');
  const btnSpinner = document.getElementById('btnSpinner');

  if (ticketForm) {
    ticketForm.addEventListener('submit', (e) => {
      // Basic HTML5 validation trigger
      if (!ticketForm.checkValidity()) {
        return;
      }
      
      // Prevent double submit and display AI feedback
      submitBtn.disabled = true;
      btnSpinner.classList.remove('d-none');
      btnText.textContent = 'Analyzing & Submitting...';
    });
  }
});