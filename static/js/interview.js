class InterviewApp {
  constructor() {
    console.log("🔥 InterviewApp v3.13 - Audio Debug + Session Fix");
    this.websocket = null;
    this.proctoringWebSocket = null;
    this.proctoringSessionId = null;
    this.audioContext = null;
    this.mediaRecorder = null;
    this.mediaStream = null;
    this.audioChunks = [];
    this.isRecording = false;
    this.avatar = "default.png";
    this.inactivityTimer = null;
    this.INACTIVITY_TIMEOUT = 30000; // 30 seconds inactivity threshold
    this.isWaitingForResponse = false;
    this.interimTranscript = "";
    this.finalTranscript = "";
    this.recognition = null;
    this.sarvamSTT = null; // Sarvam STT WebSocket client
    this.isEditing = false;
    this.liveTranscriptElement = null;
    this.websocketIsAlive = false;
    this.currentQuestionNumber = 1;
    this.isPlayingAudio = false;
    this.isProcessingQuestion = false;
    this.interviewEnded = false;
    this.currentEvaluationScore = 0;
    this.totalEvaluations = 0;
    this.averageScore = 0;

    // Coding question tracking
    this.currentQuestionType = "text";
    this.isCodeEditorActive = false;

    this.answerTimerId = null;
    this.answerTimerEndTs = null;
    this.answerTimerElement = null;
    this.lastQuestionElement = null;

    // ADDED: Face capture system
    this.captureVideo = null;
    this.captureCanvas = null;
    this.captureContext = null;
    this.capturedImageData = null;
    this.faceCaptureDone = false;

    // ORIGINAL WORKING: Proctoring system
    this.proctoring = new PythonProctoringSystem();

    this.initElements();
    this.initEventListeners();
    this.initQuestionLog();
    this.initFaceCapture(); // ADDED

    // Monitor fullscreen changes to record exits
    document.addEventListener("fullscreenchange", () => {
      const inFullscreen = !!document.fullscreenElement;
      if (!inFullscreen && this.websocketIsAlive && !this.interviewEnded) {
        // Record fullscreen exit as a proctoring event
        fetch("/proctoring/fullscreen_event", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event: "exit_fullscreen",
            session_id: this.proctoringSessionId,
            severity: "medium",
          }),
        }).catch(() => { });
        this.showStatus(
          "Fullscreen exited detected. Please stay in fullscreen mode.",
          "warning"
        );
      }
    });
  }

  initQuestionLog() {
    console.log("Interview question logging initialized");
  }

  logQuestion(question) {
    const timestamp = new Date()
      .toISOString()
      .replace("T", " ")
      .substring(0, 19);
    const logEntry = {
      timestamp: timestamp,
      questionNumber: this.currentQuestionNumber,
      question: question,
    };
    console.log(
      `[${timestamp}] Question ${this.currentQuestionNumber}: "${question}"`
    );
    this.currentQuestionNumber += 1;
  }

  initElements() {
    // ORIGINAL WORKING ELEMENTS
    this.elements = {
      startBtn: document.getElementById("start-interview-btn"),
      uploadForm: document.getElementById("upload-form"),
      resumeInput: document.getElementById("resume"),
      avatarSelect: document.getElementById("avatar"),
      interviewContainer: document.getElementById("interview-container"),
      transcriptContainer: document.getElementById("transcript-container"),
      recordBtn: document.getElementById("record-btn"),
      sendTextBtn: document.getElementById("send-text-btn"),
      userTextInput: document.getElementById("user-text-input"),
      statusIndicator: document.getElementById("status-indicator"),
      audioPlayer: document.getElementById("audio-player"),
      interviewerAvatar: document.getElementById("interviewer-avatar"),
      submitResponseBtn: document.getElementById("submit-response-btn"),
      endInterviewBtn: document.createElement("button"),
      loadingIndicator: document.createElement("div"),
      editControls: document.createElement("div"),
      editTextarea: document.createElement("textarea"),
      confirmEditBtn: document.createElement("button"),
      cancelEditBtn: document.createElement("button"),
    };

    // ORIGINAL WORKING: End Interview Button
    this.elements.endInterviewBtn.id = "end-interview-btn";
    this.elements.endInterviewBtn.textContent = "End Interview";
    this.elements.endInterviewBtn.className = "btn-end-interview";
    this.elements.interviewContainer.appendChild(this.elements.endInterviewBtn);

    // ORIGINAL WORKING: Loading Indicator (hidden - no status message)
    this.elements.loadingIndicator.className = "loading-indicator";
    this.elements.loadingIndicator.innerHTML = '<div class="spinner"></div>';
    this.elements.loadingIndicator.style.display = "none";
    this.elements.interviewContainer.appendChild(
      this.elements.loadingIndicator
    );

    // Score tracking is kept in the background for reporting purposes

    // ORIGINAL WORKING: Edit Controls
    this.elements.editControls.className = "edit-controls";
    this.elements.editControls.style.display = "none";
    this.elements.editTextarea.className = "edit-textarea";
    this.elements.editTextarea.placeholder = "Edit your response...";
    this.elements.confirmEditBtn.textContent = "Send";
    this.elements.confirmEditBtn.className = "btn-confirm-edit";
    this.elements.cancelEditBtn.textContent = "Cancel";
    this.elements.cancelEditBtn.className = "btn-cancel-edit";

    this.elements.editControls.appendChild(this.elements.editTextarea);
    this.elements.editControls.appendChild(this.elements.confirmEditBtn);
    this.elements.editControls.appendChild(this.elements.cancelEditBtn);
    this.elements.interviewContainer.appendChild(this.elements.editControls);
  }

  // ADDED: Face capture initialization
  initFaceCapture() {
    this.captureVideo = document.getElementById("capture-video");
    this.captureCanvas = document.getElementById("capture-canvas");
    if (this.captureCanvas) {
      this.captureContext = this.captureCanvas.getContext("2d");
    }
  }

  initEventListeners() {
    // ORIGINAL WORKING EVENT LISTENERS
    if (this.elements.startBtn) {
      this.elements.startBtn.addEventListener("click", () =>
        this.startInterview()
      );
    }
    this.elements.recordBtn.addEventListener("click", () =>
      this.toggleRecording()
    );
    this.elements.sendTextBtn.addEventListener("click", () =>
      this.sendTextResponse()
    );
    this.elements.userTextInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.sendTextResponse();
      }
    });
    this.elements.endInterviewBtn.addEventListener("click", () =>
      this.endInterviewManually()
    );

    // Code submit button
    const submitCodeBtn = document.getElementById("submit-code-btn");
    if (submitCodeBtn) {
      submitCodeBtn.addEventListener("click", () => this.sendTextResponse());
    }

    // Submit Response button for early submission
    if (this.elements.submitResponseBtn) {
      this.elements.submitResponseBtn.addEventListener("click", () =>
        this.submitCurrentResponse()
      );
    }

    // Edit controls
    this.elements.confirmEditBtn.addEventListener("click", () =>
      this.confirmEdit()
    );
    this.elements.cancelEditBtn.addEventListener("click", () =>
      this.cancelEdit()
    );

    // ADDED: Face capture controls
    const captureBtn = document.getElementById("capture-photo-btn");
    const retakeBtn = document.getElementById("retake-photo-btn");
    const proceedBtn = document.getElementById("proceed-interview-btn");

    if (captureBtn)
      captureBtn.addEventListener("click", () => this.capturePhoto());
    if (retakeBtn)
      retakeBtn.addEventListener("click", () => this.retakePhoto());
    if (proceedBtn)
      proceedBtn.addEventListener("click", () => this.proceedToInterview());
  }

  async startInterview() {
    // ADDED: Validate user details first (required)
    const name = document.getElementById("user-name").value.trim();
    const phone = document.getElementById("user-phone").value.trim();
    const email = document.getElementById("user-email").value.trim();
    const questionsInput = document.getElementById("questions-input");
    const questionsText = questionsInput ? questionsInput.value.trim() : "";
    const params = new URLSearchParams(window.location.search);
    const jobId = params.get("job_id") || "";

    const questionsArr = questionsText
      ? questionsText
        .split("\n")
        .map((q) => q.trim())
        .filter((q) => q.length > 0)
      : [];
    this.requestFullscreenIfEnabled();
    if (!name || !phone || !email) {
      alert("Please fill in all personal information fields.");
      return;
    }
    // If launched with job_id, skip requiring manual questions
    if (questionsArr.length === 0) {
      const params = new URLSearchParams(window.location.search);
      const jobIdCheck = params.get("job_id") || "";
      if (!jobIdCheck) {
        alert("Please enter at least one interview question (one per line).");
        return;
      }
    }

    const formData = new FormData();
    // Add user details to form data
    formData.append("name", name);
    formData.append("phone", phone);
    formData.append("email", email);
    if (questionsArr.length > 0) {
      formData.append("questions", JSON.stringify(questionsArr));
    }
    if (jobId) {
      formData.append("job_id", jobId);
    }

    try {
      this.showStatus("Processing your information...", "processing");
      const response = await fetch("/start_interview", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (response.ok && data.status === "ready_for_face_capture") {
        this.proctoringSessionId = data.proctoring_session_id;
        this.showStatus("Please proceed to face verification", "processing");

        // Hide form and show face capture
        const userDetailsForm = document.getElementById("user-details-form");
        if (userDetailsForm) userDetailsForm.style.display = "none";
        if (this.elements.uploadForm)
          this.elements.uploadForm.style.display = "none";

        const faceCaptureContainer = document.getElementById(
          "face-capture-container"
        );
        if (faceCaptureContainer) {
          faceCaptureContainer.style.display = "block";
          // Initialize camera for face capture
          await this.initializeCamera();
        } else {
          // Fallback: Skip face capture if container not found
          console.warn(
            "Face capture container not found, skipping to interview"
          );
          this.skipToInterview();
        }
      } else {
        throw new Error(data.detail || "Failed to start interview");
      }
    } catch (error) {
      console.error("Error starting interview:", error);
      this.showStatus(`Error: ${error.message}`, "error");
    }
  }

  // ADDED: Skip face capture fallback
  async skipToInterview() {
    try {
      // Send dummy image data to activate session
      const dummyImage =
        "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAAAAAAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxAAPwDVAA==";

      const response = await fetch("/capture_reference_face", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          image_data: dummyImage,
        }),
      });

      if (response.ok) {
        const sessionResponse = await fetch("/start_interview_session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            proctoring_session_id: this.proctoringSessionId
          })
        });

        if (sessionResponse.ok) {
          this.proceedDirectlyToInterview();
        }
      }
    } catch (error) {
      console.error("Error in fallback:", error);
      this.proceedDirectlyToInterview();
    }
  }

  // ADDED: Initialize camera for face capture
  async initializeCamera() {
    try {
      this.showStatus(
        "Requesting camera and microphone access...",
        "processing"
      );

      // Request BOTH camera and microphone permissions during face capture
      // This prevents permission prompts during interview which would exit fullscreen
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: "user",
        },
        audio: true, // Request microphone permission now
      });

      this.captureVideo.srcObject = stream;

      // Store the stream for later use (we'll need audio during interview)
      this.initialMediaStream = stream;

      // Wait for video to load
      await new Promise((resolve) => {
        this.captureVideo.addEventListener("loadedmetadata", resolve, {
          once: true,
        });
      });

      this.showStatus("Camera ready - capture your photo", "active");
    } catch (error) {
      console.error("Error accessing camera/microphone:", error);
      this.showStatus(
        "Camera/microphone access denied. Proceeding without face verification...",
        "warning"
      );
      // Fallback: Skip face capture
      setTimeout(() => this.skipToInterview(), 2000);
    }
  }

  // ADDED: Capture photo
  capturePhoto() {
    try {
      if (
        !this.captureVideo ||
        !this.captureVideo.videoWidth ||
        !this.captureVideo.videoHeight
      ) {
        throw new Error(
          "Video not ready. Please wait for camera to initialize."
        );
      }

      // Set canvas dimensions to match video
      this.captureCanvas.width = this.captureVideo.videoWidth;
      this.captureCanvas.height = this.captureVideo.videoHeight;

      // Draw current frame to canvas
      this.captureContext.drawImage(
        this.captureVideo,
        0,
        0,
        this.captureCanvas.width,
        this.captureCanvas.height
      );

      // Get image data
      this.capturedImageData = this.captureCanvas.toDataURL("image/jpeg", 0.8);

      // Show preview
      const capturedPhoto = document.getElementById("captured-photo");
      if (capturedPhoto) {
        capturedPhoto.src = this.capturedImageData;
        const preview = document.querySelector(".captured-photo-preview");
        if (preview) preview.style.display = "block";
      }

      // Update controls
      const captureBtn = document.getElementById("capture-photo-btn");
      const retakeBtn = document.getElementById("retake-photo-btn");
      const proceedBtn = document.getElementById("proceed-interview-btn");

      if (captureBtn) captureBtn.style.display = "none";
      if (retakeBtn) retakeBtn.style.display = "inline-block";
      if (proceedBtn) proceedBtn.style.display = "inline-block";

      this.showStatus("Photo captured! Review and proceed", "success");
    } catch (error) {
      console.error("Error capturing photo:", error);
      this.showStatus(`Failed to capture photo: ${error.message}`, "error");
    }
  }

  // ADDED: Retake photo
  retakePhoto() {
    // Reset controls
    const captureBtn = document.getElementById("capture-photo-btn");
    const retakeBtn = document.getElementById("retake-photo-btn");
    const proceedBtn = document.getElementById("proceed-interview-btn");
    const preview = document.querySelector(".captured-photo-preview");

    if (captureBtn) captureBtn.style.display = "inline-block";
    if (retakeBtn) retakeBtn.style.display = "none";
    if (proceedBtn) proceedBtn.style.display = "none";
    if (preview) preview.style.display = "none";

    this.capturedImageData = null;
    this.showStatus("Camera ready - capture your photo", "active");
  }

  // ADDED: Proceed to interview after face capture
  async proceedToInterview() {
    if (!this.capturedImageData) {
      this.showStatus("Please capture your photo first.", "error");
      return;
    }

    try {
      this.showStatus("Verifying your identity...", "processing");

      // Send captured face to backend
      const response = await fetch("/capture_reference_face", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          image_data: this.capturedImageData,
        }),
      });

      const result = await response.json();

      if (response.ok && result.status === "success") {
        // Start interview session with session_id
        const sessionResponse = await fetch("/start_interview_session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            proctoring_session_id: this.proctoringSessionId
          })
        });

        if (sessionResponse.ok) {
          this.proceedDirectlyToInterview();
        } else {
          throw new Error("Failed to start interview session");
        }
      } else {
        throw new Error(result.message || "Failed to verify identity");
      }
    } catch (error) {
      console.error("Error proceeding to interview:", error);
      this.showStatus(`Error: ${error.message}`, "error");
      // Fallback: Proceed anyway after a delay
      setTimeout(() => {
        if (confirm("Would you like to proceed without face verification?")) {
          this.proceedDirectlyToInterview();
        }
      }, 2000);
    }
  }

  // ADDED: Proceed directly to interview
  proceedDirectlyToInterview() {
    this.faceCaptureDone = true;
    this.requestFullscreenIfEnabled();
    // Hide face capture
    const faceContainer = document.getElementById("face-capture-container");
    if (faceContainer) faceContainer.style.display = "none";
    // Show interview container
    this.elements.interviewContainer.style.display = "block";
    // Hide progress bar
    document.dispatchEvent(new Event("interviewStarted"));
    // Stop capture camera stream
    if (this.captureVideo && this.captureVideo.srcObject) {
      const tracks = this.captureVideo.srcObject.getTracks();
      tracks.forEach((track) => track.stop());
    }
    // Initialize proctoring system and connect LiveKit Room
    this.proctoring.initialize(this.proctoringSessionId).then(() => {
      this.connectLiveKitRoom();
    });
  }

  // Request fullscreen if URL has fullscreen=1
  requestFullscreenIfEnabled() {
    try {
      const params = new URLSearchParams(window.location.search);
      const shouldFullscreen = params.get("fullscreen") === "1";
      if (!shouldFullscreen) return;
      const elem = document.documentElement;
      if (elem.requestFullscreen) elem.requestFullscreen();
      else if (elem.webkitRequestFullscreen) elem.webkitRequestFullscreen();
      else if (elem.msRequestFullscreen) elem.msRequestFullscreen();
    } catch (e) {
      // ignore failures
    }
  }

  async connectLiveKitRoom() {
    // Connect to LiveKit room instead of WebSocket
    const sessionId = this.proctoringSessionId || new URLSearchParams(window.location.search).get('session_id');
    if (!sessionId) {
      console.error("No session ID available for LiveKit connection");
      this.showStatus("Error: Session not found", "error");
      return;
    }

    try {
      console.log(`🔗 Connecting to LiveKit room for session: ${sessionId}`);

      // Get LiveKit room info and token from backend
      const response = await fetch(`/start_interview_session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          proctoring_session_id: sessionId
        })
      });

      if (!response.ok) {
        throw new Error("Failed to get LiveKit room info");
      }

      const data = await response.json();

      if (!data.livekit_token || !data.livekit_url) {
        console.warn("LiveKit not configured, falling back to WebSocket");
        this.connectWebSocketFallback();
        return;
      }

      console.log(`✅ LiveKit room: ${data.livekit_room_name}`);

      // Initialize LiveKit Room
      this.livekitRoom = new LivekitClient.Room({
        adaptiveStream: true,
        dynacast: true,
      });

      this.websocketIsAlive = true;

      // Set up event handlers
      this.livekitRoom
        .on(LivekitClient.RoomEvent.TrackSubscribed, this.handleTrackSubscribed.bind(this))
        .on(LivekitClient.RoomEvent.TrackUnsubscribed, this.handleTrackUnsubscribed.bind(this))
        .on(LivekitClient.RoomEvent.DataReceived, this.handleDataReceived.bind(this))
        .on(LivekitClient.RoomEvent.Disconnected, this.handleDisconnected.bind(this))
        .on(LivekitClient.RoomEvent.Reconnecting, () => {
          console.log("🔄 LiveKit reconnecting...");
          this.showStatus("Reconnecting...", "warning");
        })
        .on(LivekitClient.RoomEvent.Reconnected, () => {
          console.log("✅ LiveKit reconnected");
          this.showStatus("Reconnected", "active");
        });

      // Connect to the room
      await this.livekitRoom.connect(data.livekit_url, data.livekit_token);

      console.log("✅ Connected to LiveKit room");
      this.showStatus("Interview started", "active");

      // Enable microphone for audio responses
      await this.livekitRoom.localParticipant.setMicrophoneEnabled(true);

    } catch (error) {
      console.error("❌ Failed to connect to LiveKit:", error);
      this.showStatus("Connection error. Please refresh the page.", "error");
      this.websocketIsAlive = false;
    }
  }

  // LiveKit event handlers
  handleTrackSubscribed(track, publication, participant) {
    console.log(`📥 Track subscribed: ${track.kind} from ${participant.identity}`);

    if (track.kind === LivekitClient.Track.Kind.Audio) {
      // Handle audio track (interviewer's voice)
      const audioElement = track.attach();
      audioElement.play();
      console.log("🔊 Playing audio track");
    } else if (track.kind === LivekitClient.Track.Kind.Video) {
      // Handle video track if needed
      console.log("📹 Video track received");
    }
  }

  handleTrackUnsubscribed(track, publication, participant) {
    console.log(`📤 Track unsubscribed: ${track.kind}`);
    track.detach();
  }

  async handleDataReceived(payload, participant) {
    // Handle data messages (interview questions, responses, etc.)
    if (!this.websocketIsAlive) return;

    try {
      const decoder = new TextDecoder();
      const text = decoder.decode(payload);
      const data = JSON.parse(text);

      console.log("📨 Received data message:", data.type);

      if (data.type === "question" && this.isProcessingQuestion) {
        console.log("Already processing a question, ignoring duplicate");
        return;
      }

      switch (data.type) {
        case "question":
          await this.handleQuestion(data);
          break;
        case "answer_evaluation":
          this.displayEvaluationFeedback(data);
          break;
        case "processing_response":
          this.showStatus(data.content, "processing");
          break;
        case "evaluation_error":
          this.showStatus(data.content, "warning");
          break;
        case "transcription":
          this.addToTranscript("You", data.content);
          this.resetInactivityTimer();
          break;
        case "interview_concluded":
          await this.handleInterviewConclusion(data);
          break;
        case "processing_question":
          this.showLoading();
          break;
        case "error":
          this.showStatus(data.content, "error");
          this.stopRecording();
          this.isProcessingQuestion = false;
          break;
      }
    } catch (e) {
      console.error("Error processing data message:", e);
      this.isProcessingQuestion = false;
    }
  }

  handleDisconnected() {
    console.log("❌ LiveKit disconnected");
    this.websocketIsAlive = false;
    this.clearInactivityTimer();
    if (this.isRecording) {
      this.stopRecording();
    }
    if (!this.isEditing && !this.interviewEnded) {
      this.showStatus("Connection lost. Please refresh the page.", "error");
    }
  }

  // Fallback to WebSocket if LiveKit is not available
  connectWebSocketFallback() {
    // ORIGINAL WORKING WEBSOCKET CODE (updated to support HTTPS/WSS)
    // NOW WITH SESSION ID for parallel interview support
    const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const sessionId = this.proctoringSessionId || new URLSearchParams(window.location.search).get('session_id');
    if (!sessionId) {
      console.error("No session ID available for WebSocket connection");
      this.showStatus("Error: Session not found", "error");
      return;
    }
    const wsUrl = `${wsProtocol}://${window.location.host}/ws/interview?session_id=${sessionId}`;
    console.log(`Connecting to WebSocket with session ID: ${sessionId}`);
    this.websocket = new WebSocket(wsUrl);
    this.websocketIsAlive = true;

    this.websocket.onopen = () => {
      console.log("WebSocket connected");
      this.showStatus("Interview started", "active");
    };

    this.websocket.onmessage = async (event) => {
      if (!this.websocketIsAlive) return;

      try {
        const data = JSON.parse(event.data);
        console.log("Received WebSocket message:", data.type);

        if (data.type === "question" && this.isProcessingQuestion) {
          console.log("Already processing a question, ignoring duplicate");
          return;
        }

        switch (data.type) {
          case "question":
            await this.handleQuestion(data);
            break;
          case "answer_evaluation":
            this.displayEvaluationFeedback(data);
            break;
          case "processing_response":
            this.showStatus(data.content, "processing");
            break;
          case "evaluation_error":
            this.showStatus(data.content, "warning");
            break;
          case "transcription":
            this.addToTranscript("You", data.content);
            this.resetInactivityTimer();
            break;
          case "interview_concluded":
            await this.handleInterviewConclusion(data);
            break;
          case "processing_question":
            this.showLoading();
            break;
          case "error":
            this.showStatus(data.content, "error");
            this.stopRecording();
            this.isProcessingQuestion = false;
            break;
        }
      } catch (e) {
        console.error("Error processing WebSocket message:", e);
        this.isProcessingQuestion = false;
      }
    };

    this.websocket.onclose = () => {
      console.log("WebSocket disconnected");
      this.websocketIsAlive = false;
      this.clearInactivityTimer();
      if (this.isRecording) {
        this.stopRecording();
      }
      if (!this.isEditing && !this.interviewEnded) {
        this.showStatus("Connection lost. Please refresh the page.", "error");
      }
    };

    this.websocket.onerror = (error) => {
      console.error("WebSocket error:", error);
      this.websocketIsAlive = false;
      this.showStatus("Connection error", "error");
    };
  }

  // ALL FOLLOWING METHODS ARE ORIGINAL WORKING CODE

  async handleQuestion(data) {
    this.isProcessingQuestion = true;
    this.isWaitingForResponse = false;
    this.clearAnswerTimer();
    this.hideLoading();

    if (this.isRecording) {
      this.stopRecording();
      await new Promise((resolve) => setTimeout(resolve, 500));
    }

    this.lastQuestionElement = this.addToTranscript(
      "Interviewer",
      data.content
    );
    this.logQuestion(data.content);

    // Handle code editor visibility based on question type
    const codeEditorContainer = document.getElementById(
      "code-editor-container"
    );
    const codeInput = document.getElementById("code-input");
    const textInput = document.getElementById("user-text-input");

    // Store current question type
    this.currentQuestionType = data.question_type || "text";
    this.isCodeEditorActive = false;

    if (data.question_type === "coding") {
      // Show code editor for coding questions
      codeEditorContainer.classList.add("show");
      codeInput.value = ""; // Clear previous code
      codeInput.focus();
      // Update placeholder for text input
      textInput.placeholder = "Explain your approach or type your response...";

      // Show timer banner for coding questions
      const timerBanner = document.getElementById("coding-timer-banner");
      if (timerBanner) {
        timerBanner.style.display = "block";
        timerBanner.style.background =
          "linear-gradient(135deg, #667eea 0%, #764ba2 100%)";
        timerBanner.style.animation = "none";
      }

      // Track code editor activity to prevent premature auto-submission
      this.setupCodeEditorTracking(codeInput);
    } else {
      // Hide code editor for text questions
      codeEditorContainer.classList.remove("show");
      codeInput.value = "";
      textInput.placeholder = "Type your response...";

      // Hide timer banner for non-coding questions
      const timerBanner = document.getElementById("coding-timer-banner");
      const timerValue = document.getElementById("coding-timer-value");
      if (timerBanner) {
        timerBanner.style.display = "none";
      }
      if (timerValue) {
        timerValue.textContent = "--:--";
      }
    }

    // Always try to play audio, with fallback to speech synthesis
    console.log(
      `Question type: ${data.question_type}, Audio file: ${data.audio_file}`
    );

    if (data.audio_file) {
      console.log(`Attempting to play audio: /audio/${data.audio_file}`);
      await this.playAudio(data.audio_file);
      console.log("Audio playback successful");
    } else {
      console.error("❌ No audio file provided by backend!");
      this.showStatus("Audio generation failed. Please refresh and try again.", "error");
    }

    if (data.start_recording) {
      await this.startRecording();
    } else if (data.stop_recording) {
      this.stopRecording();
    }

    // Start timer based on question type (use timer from backend or defaults)
    const timerSeconds =
      data.timer_seconds || (data.question_type === "coding" ? 300 : 120);
    const isCodingQuestion = data.question_type === "coding";

    console.log(
      `📍 About to start timer: ${timerSeconds}s, isCoding: ${isCodingQuestion}, questionType: ${data.question_type}`
    );
    this.startAnswerTimer(timerSeconds, isCodingQuestion);

    // Show Submit Response button for early submission
    if (this.elements.submitResponseBtn) {
      this.elements.submitResponseBtn.style.display = "inline-block";
    }

    this.isProcessingQuestion = false;
  }

  async submitCurrentResponse() {
    // Handle early submission of current answer
    if (
      this.isProcessingQuestion ||
      this.interviewEnded ||
      this.isWaitingForResponse
    ) {
      return;
    }

    // Stop recording if active (no delay needed for manual submission)
    if (this.isRecording) {
      this.stopRecording();
    }

    // Clear the timer
    this.clearAnswerTimer();

    // Hide Submit Response button
    if (this.elements.submitResponseBtn) {
      this.elements.submitResponseBtn.style.display = "none";
    }

    // Send the current response immediately (no delay)
    this.sendTextResponse();
  }

  async handleInterviewConclusion(data) {
    // Mark interview as ended FIRST to prevent auto-sending
    this.interviewEnded = true;

    this.addToTranscript("Interviewer", data.content);
    this.clearAnswerTimer();

    // Hide Submit Response button
    if (this.elements.submitResponseBtn) {
      this.elements.submitResponseBtn.style.display = "none";
    }

    if (data.audio_file) {
      await this.playAudio(data.audio_file);
    }

    this.stopRecording();
    await this.endInterview();

    if (data.final_average_score !== undefined) {
      this.updateScoreDisplay(
        data.final_average_score,
        data.total_questions || 0
      );
    }
    // Stay on thank-you screen; do not show report to candidate
    this.showStatus(
      "Thank you for attending the interview. You may close this window.",
      "success"
    );
  }

  displayEvaluationFeedback(evaluation) {
    const feedbackDiv = document.createElement("div");
    feedbackDiv.className = "evaluation-feedback";
    feedbackDiv.innerHTML = `
            <div class="evaluation-header">
                <h4>🤖 AI Evaluation</h4>
                <span class="score-badge">Overall: ${evaluation.overall_score}/10</span>
            </div>
            <div class="score-breakdown">
                <div class="score-item">
                    <span class="score-label">Technical Accuracy:</span>
                    <span class="score-value">${evaluation.technical_accuracy}/10</span>
                </div>
                <div class="score-item">
                    <span class="score-label">Communication:</span>
                    <span class="score-value">${evaluation.communication_clarity}/10</span>
                </div>
                <div class="score-item">
                    <span class="score-label">Relevance:</span>
                    <span class="score-value">${evaluation.relevance}/10</span>
                </div>
                <div class="score-item">
                    <span class="score-label">Depth:</span>
                    <span class="score-value">${evaluation.depth}/10</span>
                </div>
            </div>
            <div class="evaluation-content">
                <div class="feedback-section">
                                        <strong>💡 Feedback:</strong> ${evaluation.feedback}
                </div>
                <div class="strengths-section">
                    <strong>✅ Strengths:</strong> ${evaluation.strengths}
                </div>
                <div class="weaknesses-section">
                    <strong>ðŸ“ˆ Areas for Improvement:</strong> ${evaluation.weaknesses}
                </div>
                <div class="running-average">
                    <strong>ðŸ“Š Running Average:</strong> ${evaluation.average_score}/10 
                    (${evaluation.total_questions_answered} questions answered)
                </div>
            </div>
        `;

    this.elements.transcriptContainer.appendChild(feedbackDiv);
    this.elements.transcriptContainer.scrollTop =
      this.elements.transcriptContainer.scrollHeight;

    this.updateScoreDisplay(
      evaluation.average_score,
      evaluation.total_questions_answered
    );
  }

  updateScoreDisplay(averageScore, questionsAnswered) {
    // Keep track of scores in memory without updating UI
    this.currentAverageScore = averageScore;
    this.totalQuestionsAnswered = questionsAnswered;
  }

  resetInactivityTimer() {
    this.clearInactivityTimer();

    // Don't start 30-second auto-submission for coding questions
    if (this.currentQuestionType === "coding") {
      return; // Only use the main timer for coding questions
    }

    this.inactivityTimer = setTimeout(() => {
      if (this.interviewEnded || this.isWaitingForResponse) {
        return;
      }

      // Additional check: don't auto-submit if code editor is active
      if (this.isCodeEditorActive) {
        return;
      }

      this.showStatus(
        "No response detected. Moving to next question...",
        "warning"
      );
      this.clearAnswerTimer();
      this.handleTimeoutSubmission();
    }, this.INACTIVITY_TIMEOUT);
  }

  clearInactivityTimer() {
    if (this.inactivityTimer) {
      clearTimeout(this.inactivityTimer);
      this.inactivityTimer = null;
    }
  }

  async toggleRecording() {
    if (this.isRecording) {
      this.stopRecording();
    } else {
      if (this.isPlayingAudio) {
        this.showStatus(
          "Please wait for the question to finish playing",
          "warning"
        );
        return;
      }
      await this.startRecording();
    }
  }

  async initializeSarvamSTT() {
    try {
      console.log("Initializing Sarvam STT...");

      // Fetch Sarvam config from backend
      const response = await fetch('/api/sarvam-config');
      if (!response.ok) {
        throw new Error('Failed to fetch Sarvam config');
      }
      const config = await response.json();

      // Initialize Sarvam STT (API key handled by backend proxy)
      this.sarvamSTT = new SarvamSTT();

      // Set up callbacks
      this.sarvamSTT.onTranscript = (transcript) => {
        console.log("📝 onTranscript called with:", transcript);
        console.log("📝 BEFORE accumulation - finalTranscript:", this.finalTranscript);

        this.resetInactivityTimer();
        // Final transcript - ACCUMULATE (don't replace)
        // This is called after each pause/phrase completion
        if (transcript && transcript.trim()) {
          // Add to accumulated final transcript with space
          if (this.finalTranscript) {
            console.log("📝 Accumulating: '" + this.finalTranscript + "' + '" + transcript + "'");
            this.finalTranscript += " " + transcript;
          } else {
            console.log("📝 First phrase:", transcript);
            this.finalTranscript = transcript;
          }
          this.interimTranscript = ""; // Clear interim when we get final
          this.updateLiveTranscript();
          console.log("📝 AFTER accumulation - finalTranscript:", this.finalTranscript);
        }

        if (this.finalTranscript.trim().length > 3) {
          this.resetInactivityTimer();
        }
      };

      this.sarvamSTT.onInterimTranscript = (transcript) => {
        this.resetInactivityTimer();
        // Interim transcript - just the current phrase being spoken
        this.interimTranscript = transcript;
        this.updateLiveTranscript();
        console.log("Interim transcript:", transcript);
      };

      this.sarvamSTT.onError = (error) => {
        console.error("Sarvam STT error:", error);
        this.showStatus("Speech recognition error", "error");
      };

      this.sarvamSTT.onStart = () => {
        console.log("Sarvam STT started");
      };

      this.sarvamSTT.onEnd = () => {
        console.log("Sarvam STT ended");
      };

      // Connect to WebSocket
      await this.sarvamSTT.connect();

      console.log("✅ Sarvam STT initialized successfully");
    } catch (error) {
      console.error("Failed to initialize Sarvam STT:", error);
      this.showStatus("Failed to initialize speech recognition", "error");
      throw error;
    }
  }

  async startRecording() {
    if (this.isPlayingAudio) {
      return;
    }

    try {
      this.interimTranscript = "";
      this.finalTranscript = "";

      // Initialize Sarvam STT if not already done
      if (!this.sarvamSTT) {
        await this.initializeSarvamSTT();
      }

      // Start recording with Sarvam STT
      await this.sarvamSTT.startRecording();

      this.isRecording = true;
      this.elements.recordBtn.textContent = "🛑";
      this.elements.recordBtn.classList.add("recording");
      this.showStatus("Recording... Speak now", "active");
      this.resetInactivityTimer();

      this.liveTranscriptElement = document.createElement("div");
      this.liveTranscriptElement.className =
        "transcript-message you live-transcript";
      this.elements.transcriptContainer.appendChild(this.liveTranscriptElement);
    } catch (error) {
      console.error("Error starting recording:", error);
      this.showStatus("Error starting recording", "error");
    }
  }

  async stopRecording() {
    console.log("stopRecording called");
    console.log("finalTranscript BEFORE stop:", this.finalTranscript);
    console.log("interimTranscript BEFORE stop:", this.interimTranscript);

    if (this.sarvamSTT) {
      // Stop recording will finalize any remaining transcript
      await this.sarvamSTT.stopRecording();

      // Small delay to ensure finalization callback completes
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    console.log("finalTranscript AFTER stop:", this.finalTranscript);
    console.log("interimTranscript AFTER stop:", this.interimTranscript);

    this.isRecording = false;
    this.elements.recordBtn.innerHTML = '<i class="fas fa-microphone"></i>';
    this.elements.recordBtn.classList.remove("recording");
    this.clearInactivityTimer();

    // Combine final and interim transcripts
    const fullTranscript = (this.finalTranscript + " " + this.interimTranscript).trim();
    console.log("fullTranscript:", fullTranscript);

    if (fullTranscript && fullTranscript.length > 3) {
      // Clear timer when user manually stops recording
      this.clearAnswerTimer();

      // Remove live transcript element
      if (this.liveTranscriptElement) {
        this.liveTranscriptElement.remove();
        this.liveTranscriptElement = null;
      }

      // Only auto-send if interview hasn't ended
      if (!this.interviewEnded) {
        console.log("Auto-sending response...");
        this.sendResponse(fullTranscript);
      } else {
        console.log("Interview ended - not sending response");
      }

      // Clear the input field to prevent double-sending
      this.elements.userTextInput.value = "";
    } else {
      console.log("No transcript to send (length:", fullTranscript.length, ")");
      if (this.liveTranscriptElement) {
        this.liveTranscriptElement.remove();
        this.liveTranscriptElement = null;
      }
    }
  }

  updateLiveTranscript() {
    if (this.liveTranscriptElement) {
      const fullTranscript = this.finalTranscript + this.interimTranscript;
      const displayText = fullTranscript.trim() || "🎤 Listening...";

      this.liveTranscriptElement.innerHTML = `
                <strong>You:</strong> 
                <span class="message-content streaming-text">
                    ${displayText}
                    <span class="live-indicator">●</span>
                </span>
            `;
      this.elements.transcriptContainer.scrollTop =
        this.elements.transcriptContainer.scrollHeight;
    }
  }

  sendTextResponse() {
    const text = this.elements.userTextInput.value.trim();
    const codeInput = document.getElementById("code-input");
    const codeEditorContainer = document.getElementById(
      "code-editor-container"
    );

    // Check if code editor is visible (coding question)
    const isCodingQuestion =
      codeEditorContainer && codeEditorContainer.classList.contains("show");
    const code = isCodingQuestion && codeInput ? codeInput.value.trim() : "";

    // Combine text response and code
    let fullResponse = text;
    if (code) {
      fullResponse = text
        ? `${text}\n\n[CODE]\n${code}\n[/CODE]`
        : `[CODE]\n${code}\n[/CODE]`;
    }

    if (fullResponse) {
      this.sendResponse(fullResponse);
      this.elements.userTextInput.value = "";
      if (codeInput) {
        codeInput.value = "";
      }
    }
  }

  sendResponse(text) {
    if (!text || text.trim().length < 3) {
      this.showStatus("Please provide a more detailed response", "warning");
      return;
    }

    console.log("sendResponse called with text:", text);

    // Clear timer when user manually submits
    this.clearAnswerTimer();

    // Add to transcript FIRST before sending
    console.log("Adding to transcript...");
    const messageElement = this.addToTranscript("You", text);
    console.log("Message added to transcript:", messageElement);

    // Try LiveKit Data Channel first, fallback to WebSocket
    if (this.livekitRoom && this.livekitRoom.state === LivekitClient.ConnectionState.Connected) {
      console.log("Sending via LiveKit Data Channel...");
      const encoder = new TextEncoder();
      const data = encoder.encode(JSON.stringify({
        type: "text_response",
        content: text.trim(),
      }));

      this.livekitRoom.localParticipant.publishData(data, LivekitClient.DataPacket_Kind.RELIABLE);
      this.isWaitingForResponse = true;
      this.showLoading();
    } else if (
      this.websocket &&
      this.websocketIsAlive &&
      this.websocket.readyState === WebSocket.OPEN
    ) {
      console.log("Sending to WebSocket (fallback)...");
      this.websocket.send(
        JSON.stringify({
          type: "text_response",
          content: text.trim(),
        })
      );
      this.isWaitingForResponse = true;
      this.showLoading();
    } else {
      console.error("No active connection:", {
        livekitConnected: this.livekitRoom?.state === LivekitClient.ConnectionState.Connected,
        websocketExists: !!this.websocket,
        websocketAlive: this.websocketIsAlive,
        websocketReadyState: this.websocket?.readyState
      });
      this.showStatus("Connection lost. Please refresh the page.", "error");
    }
  }

  addToTranscript(speaker, message) {
    console.log(`addToTranscript called: ${speaker} - ${message.substring(0, 50)}...`);

    const messageDiv = document.createElement("div");
    messageDiv.className = `transcript-message ${speaker.toLowerCase()}`;

    const timestamp = new Date().toLocaleTimeString();
    messageDiv.innerHTML = `
            <div class="message-content">
                <strong>${speaker}:</strong> ${message}
                <span class="timestamp">${timestamp}</span>
                ${speaker === "You"
        ? '<button class="edit-btn" onclick="app.editMessage(this)">✏️</button>'
        : ""
      }
            </div>
        `;

    console.log("Appending message to transcript container...");
    this.elements.transcriptContainer.appendChild(messageDiv);
    console.log("Message appended. Total messages:", this.elements.transcriptContainer.children.length);

    this.elements.transcriptContainer.scrollTop =
      this.elements.transcriptContainer.scrollHeight;
    return messageDiv;
  }

  editMessage(button) {
    const messageDiv = button.closest(".transcript-message");
    const messageContent = messageDiv.querySelector(".message-content");
    const originalText = messageContent.textContent
      .replace(/^You:\s*/, "")
      .replace(/\d{1,2}:\d{2}:\d{2}\s*(AM|PM)\s*âœï¸$/, "")
      .trim();

    this.elements.editTextarea.value = originalText;
    this.elements.editControls.style.display = "block";
    this.isEditing = true;
    this.currentEditingMessage = messageDiv;
  }

  confirmEdit() {
    const newText = this.elements.editTextarea.value.trim();
    if (newText && newText.length > 3) {
      const messageContent =
        this.currentEditingMessage.querySelector(".message-content");
      const timestamp = new Date().toLocaleTimeString();
      messageContent.innerHTML = `
                <strong>You:</strong> ${newText}
                <span class="timestamp">${timestamp} (edited)</span>
                <button class="edit-btn" onclick="app.editMessage(this)">âœï¸</button>
            `;

      this.sendResponse(newText);
    }
    this.cancelEdit();
  }

  cancelEdit() {
    this.elements.editControls.style.display = "none";
    this.elements.editTextarea.value = "";
    this.isEditing = false;
    this.currentEditingMessage = null;
  }

  async playAudio(filename) {
    try {
      this.isPlayingAudio = true;
      this.elements.audioPlayer.src = `/audio/${filename}`;

      const aiAvatar = document.getElementById("interviewer-avatar");
      const aiIndicator = document.querySelector(
        ".ai-avatar-box .speaking-indicator"
      );

      if (aiAvatar) {
        aiAvatar.classList.add("ai-speaking", "blinking");
      }
      if (aiIndicator) {
        aiIndicator.classList.add("ai-speaking");
      }

      await new Promise((resolve, reject) => {
        this.elements.audioPlayer.onended = () => {
          this.isPlayingAudio = false;

          if (aiAvatar) {
            aiAvatar.classList.remove("ai-speaking", "blinking");
          }
          if (aiIndicator) {
            aiIndicator.classList.remove("ai-speaking");
          }

          resolve();
        };
        this.elements.audioPlayer.onerror = (err) => {
          console.error("❌ Audio player error:", err);
          this.isPlayingAudio = false;
          reject(new Error(`Audio load failed: ${err.message || 'Unknown error'}`));
        };

        // Try to play audio
        const playPromise = this.elements.audioPlayer.play();

        if (playPromise !== undefined) {
          playPromise
            .then(() => {
              console.log("✅ Audio playback started successfully");
            })
            .catch((err) => {
              console.error("❌ Audio autoplay blocked:", err.name, err.message);
              this.isPlayingAudio = false;
              reject(new Error(`Autoplay blocked: ${err.message}`));
            });
        }
      });
    } catch (error) {
      console.error("❌ Error playing audio:", error.message || error);
      this.isPlayingAudio = false;
      // Re-throw so handleQuestion can catch and use fallback
      throw error;
    }
  }

  speakTextFallback(text) {
    // Use browser's speech synthesis as fallback
    if ("speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;
      window.speechSynthesis.speak(utterance);
      console.log(
        "Using speech synthesis fallback for:",
        text.substring(0, 50)
      );
    } else {
      console.warn("Speech synthesis not supported, skipping audio");
    }
  }

  showLoading() {
    // Don't show loading indicator - removed per user request
    // this.elements.loadingIndicator.style.display = 'block';
  }

  hideLoading() {
    // Loading indicator disabled
    // this.elements.loadingIndicator.style.display = 'none';
  }

  showStatus(message, type) {
    this.elements.statusIndicator.textContent = message;
    this.elements.statusIndicator.className = `status ${type}`;

    if (type !== "error") {
      setTimeout(() => {
        if (this.elements.statusIndicator.textContent === message) {
          this.elements.statusIndicator.textContent = "";
          this.elements.statusIndicator.className = "status";
        }
      }, 5000);
    }
  }

  endInterviewManually() {
    // First, submit any pending code/response before ending
    const codeInput = document.getElementById("code-input");
    const textInput = this.elements.userTextInput;

    const code =
      this.currentQuestionType === "coding" && codeInput
        ? codeInput.value.trim()
        : "";
    const text = textInput ? textInput.value.trim() : "";

    // If there's unsaved code or text, submit it first
    if (code || text) {
      let content = text;
      if (code) {
        content = text
          ? `${text}\n\n[CODE]\n${code}\n[/CODE]`
          : `[CODE]\n${code}\n[/CODE]`;
      }

      if (
        content &&
        this.websocket &&
        this.websocketIsAlive &&
        this.websocket.readyState === WebSocket.OPEN
      ) {
        this.websocket.send(
          JSON.stringify({
            type: "text_response",
            content: content.trim(),
          })
        );

        // Clear inputs
        if (codeInput) codeInput.value = "";
        if (textInput) textInput.value = "";

        // Wait a moment for submission to process
        setTimeout(() => {
          this.sendEndInterviewSignal();
        }, 500);
        return;
      }
    }

    // No pending content, end immediately
    this.sendEndInterviewSignal();
  }

  sendEndInterviewSignal() {
    if (
      this.websocket &&
      this.websocketIsAlive &&
      this.websocket.readyState === WebSocket.OPEN
    ) {
      this.websocket.send(
        JSON.stringify({
          type: "end_interview",
        })
      );
    }
  }

  async endInterview() {
    this.interviewEnded = true;
    this.stopRecording();
    this.clearInactivityTimer();
    this.clearAnswerTimer();

    // Stop proctoring
    this.proctoring.stop();

    if (this.websocket) {
      this.websocket.close();
    }

    this.showStatus("Interview completed! Generating report...", "success");
    this.elements.endInterviewBtn.style.display = "none";
    this.elements.recordBtn.disabled = true;
    this.elements.sendTextBtn.disabled = true;
    this.elements.userTextInput.disabled = true;
  }

  startAnswerTimer(seconds, isCoding = false) {
    try {
      console.log(
        `🕐 startAnswerTimer called: ${seconds} seconds, isCoding: ${isCoding}`
      );
      this.clearAnswerTimer();

      // Create timer element
      const timer = document.createElement("div");
      timer.className = "answer-timer";

      const label = document.createElement("span");
      label.className = "timer-label";
      label.textContent = "⏱️ Time remaining:";

      const value = document.createElement("span");
      value.id = "timer-value";
      value.className = "timer-count";

      timer.appendChild(label);
      timer.appendChild(value);

      // Append timer directly after the question message content
      if (this.lastQuestionElement && this.lastQuestionElement.parentNode) {
        this.lastQuestionElement.parentNode.insertBefore(
          timer,
          this.lastQuestionElement.nextSibling
        );
      } else {
        this.elements.transcriptContainer.appendChild(timer);
      }

      this.answerTimerElement = timer;
      const endTs = Date.now() + seconds * 1000;
      this.answerTimerEndTs = endTs;

      const format = (s) => {
        const m = Math.floor(s / 60);
        const ss = s % 60;
        return `${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
      };

      if (isCoding) {
        console.log(
          `📍 Initial timer update: format(${seconds}) = ${format(seconds)}`
        );
        this.updateCodeTimerDisplay(format(seconds), seconds);

        // Verify the display was set
        const timerValue = document.getElementById("coding-timer-value");
        const timerBanner = document.getElementById("coding-timer-banner");
        console.log(
          `📍 After initial update - Banner display: ${timerBanner?.style.display}, Value: ${timerValue?.textContent}`
        );
      }

      const tick = () => {
        if (!this.answerTimerElement || !this.answerTimerElement.parentNode) {
          // Timer was removed, clear interval
          if (this.answerTimerId) {
            clearInterval(this.answerTimerId);
            this.answerTimerId = null;
          }
          return;
        }

        const remainingMs = Math.max(0, this.answerTimerEndTs - Date.now());
        const remainingSec = Math.ceil(remainingMs / 1000);
        const display = format(remainingSec);

        // Update timer display with color change when time is running out
        const valEl = timer.querySelector("#timer-value");
        if (valEl) {
          valEl.textContent = display;
          // Remove all warning classes first
          timer.classList.remove("warning", "danger");

          if (remainingSec <= 10) {
            // Red when less than 10 seconds
            timer.classList.add("danger");
          } else if (remainingSec <= 30) {
            // Orange when less than 30 seconds
            timer.classList.add("warning");
          }
        }

        if (isCoding) {
          this.updateCodeTimerDisplay(display, remainingSec);
        }

        if (remainingMs <= 0) {
          this.clearAnswerTimer();
          this.autoSubmitOnTimeout();
        }
      };

      // Initial tick and set interval
      tick();
      this.answerTimerId = setInterval(tick, 1000);
    } catch (e) {
      console.error("Error starting answer timer:", e);
    }
  }

  updateCodeTimerDisplay(display, remainingSec) {
    // Update the prominent timer banner
    const timerValue = document.getElementById("coding-timer-value");
    const timerBanner = document.getElementById("coding-timer-banner");

    if (!timerValue || !timerBanner) {
      console.error("❌ Coding timer elements not found!", {
        timerValue,
        timerBanner,
      });
      return;
    }

    // Ensure banner is visible (in case clearAnswerTimer hid it)
    timerBanner.style.display = "block";
    timerValue.textContent = display;
    console.log(
      `⏰ Coding timer updated: ${display} (${remainingSec}s remaining)`
    );

    if (remainingSec === null || remainingSec === undefined) {
      timerBanner.style.background =
        "linear-gradient(135deg, #667eea 0%, #764ba2 100%)";
      return;
    }

    // Color coding based on time remaining
    if (remainingSec <= 10) {
      timerBanner.style.background =
        "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)";
      timerBanner.style.animation = "pulse 1s infinite";
    } else if (remainingSec <= 30) {
      timerBanner.style.background =
        "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)";
      timerBanner.style.animation = "none";
    } else {
      timerBanner.style.background =
        "linear-gradient(135deg, #667eea 0%, #764ba2 100%)";
      timerBanner.style.animation = "none";
    }
  }

  clearAnswerTimer() {
    if (this.answerTimerId) {
      clearInterval(this.answerTimerId);
      this.answerTimerId = null;
    }
    if (this.answerTimerElement) {
      if (this.answerTimerElement.parentNode) {
        this.answerTimerElement.parentNode.removeChild(this.answerTimerElement);
      }
      this.answerTimerElement = null;
    }
    this.answerTimerEndTs = null;

    // Hide the coding timer banner when clearing timer
    const timerBanner = document.getElementById("coding-timer-banner");
    const timerValue = document.getElementById("coding-timer-value");
    if (timerBanner) {
      timerBanner.style.display = "none";
    }
    if (timerValue) {
      timerValue.textContent = "--:--";
    }
  }

  autoSubmitOnTimeout() {
    try {
      if (this.interviewEnded) return;

      // Show notification that time is up
      this.showStatus(
        "Time's up! Submitting your answer and moving to next question...",
        "warning"
      );

      // Directly handle timeout submission (it will stop recording if needed)
      this.handleTimeoutSubmission();
    } catch (e) {
      console.error("Error in autoSubmitOnTimeout:", e);
    }
  }

  handleTimeoutSubmission() {
    try {
      if (this.isWaitingForResponse || this.interviewEnded) {
        return;
      }

      // Helper to submit the response
      const submitResponse = () => {
        // Combine all available transcript sources (final + interim + typed)
        const voiceFinal = this.finalTranscript || "";
        const voiceInterim = this.interimTranscript || "";
        const voice = (voiceFinal + " " + voiceInterim).trim();
        const typed = this.elements.userTextInput
          ? this.elements.userTextInput.value.trim()
          : "";

        // Check for code if it's a coding question
        const codeInput = document.getElementById("code-input");
        const code =
          this.currentQuestionType === "coding" && codeInput
            ? codeInput.value.trim()
            : "";

        // Combine text and code
        let content = voice || typed || "";
        if (code) {
          content = content
            ? `${content}\n\n[CODE]\n${code}\n[/CODE]`
            : `[CODE]\n${code}\n[/CODE]`;
        }

        // Use default message if nothing provided
        if (!content) {
          content = "[No response - Time expired]";
        }

        // Clear the input field and transcripts
        if (this.elements.userTextInput) {
          this.elements.userTextInput.value = "";
        }
        // Clear code input if it's a coding question (reuse codeInput variable)
        if (codeInput) {
          codeInput.value = "";
        }
        this.finalTranscript = "";
        this.interimTranscript = "";

        // Remove live transcript element if it exists
        if (this.liveTranscriptElement) {
          this.liveTranscriptElement.remove();
          this.liveTranscriptElement = null;
        }

        if (
          this.websocket &&
          this.websocketIsAlive &&
          this.websocket.readyState === WebSocket.OPEN
        ) {
          this.websocket.send(
            JSON.stringify({
              type: "text_response",
              content: content,
              timeout_submission: true, // Flag to indicate this is from timeout
            })
          );
          this.isWaitingForResponse = true;

          // Always add to transcript to show what was submitted
          this.addToTranscript("You", content);
        }
      };

      // Stop recording if active to capture final transcript
      if (this.isRecording && this.recognition) {
        // Stop recognition to finalize any pending results
        this.recognition.stop();
        this.isRecording = false;
        this.elements.recordBtn.innerHTML = '<i class="fas fa-microphone"></i>';
        this.elements.recordBtn.classList.remove("recording");
        this.clearInactivityTimer();

        // Wait a moment for recognition to process final results, then submit
        setTimeout(() => {
          submitResponse();
        }, 300);
      } else {
        // Not recording, submit immediately
        submitResponse();
      }
    } catch (e) {
      console.error("Error in handleTimeoutSubmission:", e);
    }
  }

  setupCodeEditorTracking(codeInput) {
    // Track when user is actively typing in code editor
    let typingTimeout;

    const handleCodeInput = () => {
      this.isCodeEditorActive = true;

      // Clear existing timeout
      if (typingTimeout) {
        clearTimeout(typingTimeout);
      }

      // Set flag to false after 3 seconds of no typing
      typingTimeout = setTimeout(() => {
        this.isCodeEditorActive = false;
      }, 3000);
    };

    // Remove old listeners if they exist
    if (codeInput._codeInputHandler) {
      codeInput.removeEventListener("input", codeInput._codeInputHandler);
      codeInput.removeEventListener("keydown", codeInput._codeInputHandler);
    }

    // Add new listeners
    codeInput._codeInputHandler = handleCodeInput;
    codeInput.addEventListener("input", handleCodeInput);
    codeInput.addEventListener("keydown", handleCodeInput);
  }
}

// ORIGINAL WORKING PROCTORING SYSTEM + Face matching capability
class PythonProctoringSystem {
  constructor() {
    this.websocket = null;
    this.sessionId = null;
    this.isActive = false;
    this.sessionActive = true;
    this.initElements();
  }

  initElements() {
    this.video = document.getElementById("student-video");
    this.canvas = document.getElementById("face-canvas");
    if (this.canvas) {
      this.ctx = this.canvas.getContext("2d");
      this.canvas.style.display = "none";
    }

    this.statusElements = {
      warningCount: document.getElementById("warning-count"),
      gazeDirection: document.getElementById("gaze-direction"),
      warningMessage: document.getElementById("warning-message"),
      warningTimer: document.getElementById("warning-timer"),
      proctorWarnings: document.getElementById("proctor-warnings"),
    };
  }

  async initialize(sessionId) {
    try {
      this.sessionId = sessionId;
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 },
      });
      this.video.srcObject = stream;
      this.connectWebSocket();
      this.video.addEventListener("loadeddata", () => {
        if (this.canvas) {
          this.canvas.width = this.video.videoWidth;
          this.canvas.height = this.video.videoHeight;
        }
        this.startProcessing();
      });
      this.isActive = true;
      console.log("Python proctoring system initialized");
    } catch (error) {
      console.error("Error initializing Python proctoring system:", error);
    }
  }

  connectWebSocket() {
    // Use wss:// for HTTPS pages, ws:// for HTTP
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${protocol}://${window.location.host}/ws/proctoring?session_id=${this.sessionId}`;

    this.websocket = new WebSocket(wsUrl);
    this.websocket.onopen = () => {
      console.log("Proctoring WebSocket connected");
    };
    this.websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleProctoringResponse(data);
    };
    this.websocket.onclose = () =>
      console.log("Proctoring WebSocket disconnected");
    this.websocket.onerror = (error) =>
      console.error("Proctoring WebSocket error:", error);
  }

  startProcessing() {
    const processFrame = () => {
      if (!this.isActive || !this.sessionActive) return;
      if (this.video.readyState >= 2 && this.canvas && this.ctx) {
        this.ctx.drawImage(
          this.video,
          0,
          0,
          this.canvas.width,
          this.canvas.height
        );
        const imageData = this.canvas.toDataURL("image/jpeg", 0.8);
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
          this.websocket.send(
            JSON.stringify({
              type: "process_frame",
              session_id: this.sessionId,
              image_data: imageData,
            })
          );
        }
      }
      if (this.sessionActive) {
        setTimeout(processFrame, 100);
      }
    };
    processFrame();
  }
  handleProctoringResponse(data) {
    try {
      if (data.type === "reference_face_response") {
        const result = data.result;
        if (result.status === "success") {
          console.log("Reference face processed successfully");
        } else {
          console.warn("Failed to process reference face:", result.message);
        }
      } else if (data.type === "proctoring_result") {
        const result = data.result;
        if (result.status === "success") {
          // Update display elements
          this.updateGazeDisplay(result.gaze_direction || "UNKNOWN");
          this.updateWarningCount(
            result.violation_count || 0,
            result.max_violations || 3
          );

          // FIXED: Handle violations OR hide warnings if none
          if (result.violations && result.violations.length > 0) {
            this.handleViolations(result.violations);
          } else {
            // FIXED: No violations - immediately hide warnings
            this.hideWarning();
          }

          // Check if session should be terminated
          if (!result.session_active) {
            this.terminateSession();
          }
        } else if (result.status === "inactive") {
          // Session is inactive, silently ignore
          console.debug("Proctoring session inactive");
        } else if (result.status === "error") {
          console.error("Proctoring error:", result.message || "Unknown error");
        }
      } else if (data.type === "error") {
        console.error("Proctoring error:", data.message);
      }
    } catch (error) {
      console.error("Error handling proctoring response:", error);
    }
  }

  handleViolations(violations) {
    let hasActiveWarnings = false;

    violations.forEach((violation) => {
      console.log("Proctoring violation:", violation.type, violation.message);

      if (violation.type === "warning") {
        this.showWarning(violation.message, violation.timer || "");
        hasActiveWarnings = true;
      } else if (violation.type === "violation") {
        this.addViolationEffect();
        console.warn(`VIOLATION RECORDED: ${violation.message}`);
      } else if (violation.type === "session_terminated") {
        this.terminateSession();
      }
    });

    // FIXED: Hide warnings immediately if no active warnings
    if (!hasActiveWarnings) {
      this.hideWarning();
    }
  }

  addViolationEffect() {
    const cameraBox = document.querySelector(".student-camera-box");
    if (cameraBox) {
      cameraBox.classList.add("violation");
      setTimeout(() => cameraBox.classList.remove("violation"), 2000);
    }
  }

  terminateSession() {
    this.sessionActive = false;
    this.isActive = false;
    this.showWarning("SESSION TERMINATED", "Too many violations detected!");
    if (this.statusElements.proctorWarnings) {
      this.statusElements.proctorWarnings.style.background =
        "rgba(139, 0, 0, 0.95)";
    }
    console.log("SESSION TERMINATED: Too many violations detected!");
    setTimeout(() => {
      const params = new URLSearchParams(window.location.search);
      const sessionId = params.get("session_id") || this.proctoringSessionId;
      if (sessionId) {
        window.location.href = `/report/${sessionId}`;
      } else {
        window.location.href = "/report";
      }
    }, 3000);
  }

  showWarning(message, timer) {
    if (this.statusElements.warningMessage) {
      this.statusElements.warningMessage.textContent = message;
    }
    if (this.statusElements.warningTimer) {
      this.statusElements.warningTimer.textContent = timer;
    }
    if (this.statusElements.proctorWarnings) {
      this.statusElements.proctorWarnings.classList.add("show");
    }
  }

  hideWarning() {
    if (this.statusElements.proctorWarnings) {
      this.statusElements.proctorWarnings.classList.remove("show");
    }
  }

  updateGazeDisplay(direction) {
    if (this.statusElements.gazeDirection) {
      this.statusElements.gazeDirection.textContent = direction;
    }
  }

  updateWarningCount(current, max) {
    if (this.statusElements.warningCount) {
      this.statusElements.warningCount.textContent = `${current}/${max}`;
    }
  }

  stop() {
    this.isActive = false;
    this.sessionActive = false;
    if (this.video && this.video.srcObject) {
      const tracks = this.video.srcObject.getTracks();
      tracks.forEach((track) => track.stop());
    }
    if (this.websocket) {
      this.websocket.close();
    }
    console.log("Python proctoring system stopped");
  }
}

// Initialize the app when the page loads
let app;
document.addEventListener("DOMContentLoaded", () => {
  app = new InterviewApp();
});
