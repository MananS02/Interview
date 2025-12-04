/**
 * Sarvam STT WebSocket Integration
 * Real-time speech-to-text using Sarvam Saaras v2.5 model
 */

class SarvamSTT {
  constructor(apiKey) {
    console.log("🔥 SarvamSTT v3.2 - Timing Fix Applied");
    this.apiKey = apiKey;
    this.websocket = null;
    this.isActive = false;
    this.mediaRecorder = null;
    this.audioContext = null;
    this.processor = null;
    this.stream = null;
    
    // Callbacks
    this.onTranscript = null;
    this.onInterimTranscript = null;
    this.onError = null;
    this.onStart = null;
    this.onEnd = null;
    
    // Configuration
    this.model = "saaras:v2.5";
    this.sampleRate = 16000;
    this.encoding = "audio/wav";
    
    // Track last interim transcript for END_SPEECH finalization
    this.lastInterimTranscript = "";
  }

  /**
   * Initialize and connect to Sarvam STT WebSocket via backend proxy
   */
  async connect() {
    try {
      // Connect to backend proxy which handles API key authentication
      const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
      const wsUrl = `${wsProtocol}://${window.location.host}/ws/sarvam-stt`;

      console.log("Connecting to Sarvam STT proxy:", wsUrl);

      // Create WebSocket connection to backend proxy
      this.websocket = new WebSocket(wsUrl);
      
      this.websocket.onopen = () => {
        console.log("✅ Sarvam STT WebSocket connected");
        this.isActive = true;
        
        // Send config message with API key
        this.sendConfig();
        
        if (this.onStart) this.onStart();
      };

      this.websocket.onmessage = (event) => {
        this.handleMessage(event.data);
      };

      this.websocket.onerror = (error) => {
        console.error("❌ Sarvam STT WebSocket error:", error);
        if (this.onError) this.onError(error);
      };

      this.websocket.onclose = () => {
        console.log("Sarvam STT WebSocket closed");
        this.isActive = false;
        if (this.onEnd) this.onEnd();
      };

    } catch (error) {
      console.error("Failed to connect to Sarvam STT:", error);
      if (this.onError) this.onError(error);
    }
  }

  /**
   * Send configuration message
   */
  sendConfig() {
    if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
      return;
    }

    const configMessage = {
      type: "config",
      prompt: "" // Optional: Add context prompt if needed
    };

    this.websocket.send(JSON.stringify(configMessage));
    console.log("Sent config to Sarvam STT");
  }

  /**
   * Handle incoming WebSocket messages
   */
  handleMessage(data) {
    try {
      const message = JSON.parse(data);
      console.log("Sarvam STT message:", message);

      if (message.type === "data") {
        // Transcription data - treat as interim
        const transcript = message.data?.transcript || "";

        if (transcript) {
          // Store for END_SPEECH finalization
          this.lastInterimTranscript = transcript;
          
          if (this.onInterimTranscript) {
            this.onInterimTranscript(transcript);
          }
        }
      } else if (message.type === "error") {
        console.error("Sarvam STT error:", message.data);
        if (this.onError) this.onError(message.data);
      } else if (message.type === "events") {
        // VAD events (START_SPEECH, END_SPEECH)
        const signalType = message.data?.signal_type;
        console.log("Sarvam STT event:", signalType);
        
        if (signalType === "START_SPEECH") {
          console.log("START_SPEECH detected");
          // Finalize the PREVIOUS transcript before starting new one
          if (this.lastInterimTranscript && this.onTranscript) {
            console.log("🎯 Finalizing previous phrase:", this.lastInterimTranscript);
            this.onTranscript(this.lastInterimTranscript);
          }
          this.lastInterimTranscript = "";
        } else if (signalType === "END_SPEECH") {
          console.log("END_SPEECH detected - transcript will arrive next");
          // Don't finalize here - transcript data comes AFTER this event
        }
      }
    } catch (error) {
      console.error("Error parsing Sarvam STT message:", error);
    }
  }

  /**
   * Start capturing and streaming audio
   */
  async startRecording() {
    try {
      // Get microphone access
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: this.sampleRate,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      // Create audio context
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: this.sampleRate
      });

      const source = this.audioContext.createMediaStreamSource(this.stream);
      
      // Create script processor for audio chunks
      const bufferSize = 4096;
      this.processor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

      this.processor.onaudioprocess = (e) => {
        if (!this.isActive || !this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
          return;
        }

        const inputData = e.inputBuffer.getChannelData(0);
        
        // Convert Float32Array to Int16Array (PCM)
        const pcmData = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // Convert to base64
        const base64Audio = this.arrayBufferToBase64(pcmData.buffer);

        // Send audio message
        const audioMessage = {
          audio: {
            data: base64Audio,
            sample_rate: this.sampleRate.toString(),
            encoding: this.encoding,
            input_audio_codec: "pcm_s16le"
          }
        };

        this.websocket.send(JSON.stringify(audioMessage));
      };

      source.connect(this.processor);
      this.processor.connect(this.audioContext.destination);

      console.log("✅ Started streaming audio to Sarvam STT");

    } catch (error) {
      console.error("Failed to start recording:", error);
      if (this.onError) this.onError(error);
    }
  }

  /**
   * Stop recording and send flush signal
   */
  stopRecording() {
    // Finalize any remaining transcript before stopping
    if (this.lastInterimTranscript && this.onTranscript) {
      console.log("🎯 Finalizing last phrase on stop:", this.lastInterimTranscript);
      this.onTranscript(this.lastInterimTranscript);
      this.lastInterimTranscript = "";
    }

    // Send flush signal to finalize transcription
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
      const flushMessage = {
        type: "flush"
      };
      this.websocket.send(JSON.stringify(flushMessage));
      console.log("Sent flush signal to Sarvam STT");
    }

    // Stop audio processing
    if (this.processor) {
      this.processor.disconnect();
      this.processor = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }

    console.log("Stopped recording");
  }

  /**
   * Close WebSocket connection
   */
  disconnect() {
    this.stopRecording();
    
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }

    this.isActive = false;
  }

  /**
   * Convert ArrayBuffer to base64
   */
  arrayBufferToBase64(buffer) {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
  }
}

// Export for use in interview.js
window.SarvamSTT = SarvamSTT;
