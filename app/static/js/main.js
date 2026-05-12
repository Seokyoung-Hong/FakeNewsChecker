const form = document.getElementById("analysis-form");
const urlInput = document.getElementById("target-url");
const submitButton = document.getElementById("submit-button");
const errorElement = document.getElementById("form-error");
const errorSummaryElement = document.getElementById("form-error-summary");
const loadingOverlay = document.getElementById("loading-overlay");
const loadingCurrentStep = document.getElementById("loading-current-step");
const loadingErrorMessage = document.getElementById("loading-error-message");
const loadingStatusMessage = document.getElementById("loading-status-message");
const loadingSteps = document.querySelectorAll("#loading-steps li");
let isSubmitting = false;
let activePoll = null;
const defaultSubmitLabel = form?.dataset.submitLabel || "검증하기";

function setFormError(message) {
  if (errorElement) {
    errorElement.textContent = message;
    errorElement.classList.toggle("is-visible", Boolean(message));
  }

  if (errorSummaryElement) {
    errorSummaryElement.textContent = message;
    errorSummaryElement.classList.toggle("is-visible", Boolean(message));
  }
}

function setOverlayState(stage, completedStages = []) {
  if (loadingCurrentStep) {
    const active = Array.from(loadingSteps).find((item) => item.dataset.stage === stage);
    if (!active) {
      loadingCurrentStep.textContent = "분석 준비 중";
    } else {
      const stepLabel = active.querySelector("span:last-child")?.textContent?.trim() || "";
      loadingCurrentStep.textContent = stepLabel || "분석 준비 중";
    }
  }

  loadingSteps.forEach((item) => {
    item.classList.remove("is-active", "is-complete");
    if (completedStages.includes(item.dataset.stage)) {
      item.classList.add("is-complete");
    }
    if (item.dataset.stage === stage) {
      item.classList.add("is-active");
    }
  });
}

function setOverlayStatusMessage(message) {
  if (!loadingStatusMessage) {
    return;
  }

  const trimmedMessage = message && message.trim().length > 0 ? message.trim() : "";
  loadingStatusMessage.textContent = trimmedMessage;
}

function resetOverlay() {
  activePoll = null;
  isSubmitting = false;
  if (submitButton) {
    submitButton.disabled = false;
    submitButton.textContent = defaultSubmitLabel;
  }
  if (loadingOverlay) {
    loadingOverlay.classList.remove("is-visible");
    loadingOverlay.setAttribute("aria-hidden", "true");
  }
  if (loadingCurrentStep) {
    loadingCurrentStep.textContent = "분석 준비 중";
  }
  if (loadingErrorMessage) {
    loadingErrorMessage.textContent = "";
  }
  if (loadingStatusMessage) {
    loadingStatusMessage.textContent = "";
  }
  loadingSteps.forEach((item) => item.classList.remove("is-active", "is-complete"));
}

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function pollAnalysisStatus(statusUrl) {
  while (isSubmitting) {
    const statusResponse = await fetch(statusUrl, { method: "GET" });
    const statusPayload = await statusResponse.json();
    if (!statusResponse.ok) {
      throw new Error(statusPayload.detail || "진행 상태를 확인할 수 없습니다.");
    }

    setOverlayStatusMessage(statusPayload.status_message);
    setOverlayState(statusPayload.stage, statusPayload.completed_stages || []);

    if (statusPayload.status === "completed" && statusPayload.redirect_url) {
      activePoll = null;
      window.location.assign(statusPayload.redirect_url);
      return;
    }

    if (statusPayload.status === "failed") {
      throw new Error(statusPayload.error_message || "분석 중 오류가 발생했습니다.");
    }

    activePoll = statusUrl;
    await delay(700);
  }
}

async function startAnalysisFlow(value) {
  const startAction = form.dataset.startAction || `${form.action}/start`;
  const formData = new URLSearchParams();
  formData.set("url", value);

  const response = await fetch(startAction, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    },
    body: formData.toString(),
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error_message || "분석 시작에 실패했습니다.");
  }

    setOverlayStatusMessage(payload.status_message);
    setOverlayState(payload.stage, payload.completed_stages || []);
    await pollAnalysisStatus(payload.status_url);
  }

if (form && urlInput && submitButton && errorElement && loadingOverlay) {
  form.addEventListener("submit", (event) => {
    if (isSubmitting) {
      return;
    }

    const value = urlInput.value.trim();

    if (!value) {
      setFormError("검증할 URL을 입력해 주세요.");
      urlInput.focus();
      event.preventDefault();
      return;
    }

    if (!urlInput.checkValidity()) {
      setFormError("올바른 URL 형식으로 입력해 주세요.");
      return;
    }

    setFormError("");
    submitButton.disabled = true;
    submitButton.textContent = "검증 준비 중";
    loadingOverlay.classList.add("is-visible");
    loadingOverlay.setAttribute("aria-hidden", "false");
    setOverlayState("body_collection", []);
    loadingOverlay.getBoundingClientRect();
    isSubmitting = true;
    event.preventDefault();

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.setTimeout(async () => {
          try {
            await startAnalysisFlow(value);
          } catch (error) {
            const message = error instanceof Error ? error.message : "분석 시작에 실패했습니다.";
            if (loadingErrorMessage) {
              loadingErrorMessage.textContent = message;
            }
            setFormError(message);
            resetOverlay();
          }
        }, 80);
      });
    });
  });

  urlInput.addEventListener("input", () => {
    setFormError("");
    resetOverlay();
  });
}
