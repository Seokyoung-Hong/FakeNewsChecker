const form = document.getElementById("analysis-form");
const urlInput = document.getElementById("target-url");
const submitButton = document.getElementById("submit-button");
const errorElement = document.getElementById("form-error");
const loadingOverlay = document.getElementById("loading-overlay");
let isSubmitting = false;

if (form && urlInput && submitButton && errorElement && loadingOverlay) {
  form.addEventListener("submit", (event) => {
    if (isSubmitting) {
      return;
    }

    const value = urlInput.value.trim();

    if (!value) {
      errorElement.textContent = "검증할 URL을 입력해 주세요.";
      errorElement.classList.add("is-visible");
      urlInput.focus();
      event.preventDefault();
      return;
    }

    if (!urlInput.checkValidity()) {
      errorElement.textContent = "올바른 URL 형식으로 입력해 주세요.";
      errorElement.classList.add("is-visible");
      return;
    }

    errorElement.textContent = "";
    errorElement.classList.remove("is-visible");
    submitButton.disabled = true;
    submitButton.textContent = "분석 준비 중";
    loadingOverlay.classList.add("is-visible");
    loadingOverlay.setAttribute("aria-hidden", "false");
    loadingOverlay.getBoundingClientRect();
    isSubmitting = true;
    event.preventDefault();

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.setTimeout(() => {
          form.requestSubmit();
        }, 80);
      });
    });
  });

  urlInput.addEventListener("input", () => {
    errorElement.textContent = "";
    errorElement.classList.remove("is-visible");
    isSubmitting = false;

    if (submitButton.disabled) {
      submitButton.disabled = false;
      submitButton.textContent = "검증하기";
      loadingOverlay.classList.remove("is-visible");
      loadingOverlay.setAttribute("aria-hidden", "true");
    }
  });
}
