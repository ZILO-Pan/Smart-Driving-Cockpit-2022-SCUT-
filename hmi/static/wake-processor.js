/**
 * AudioWorklet Processor — 唤醒词监听用
 * 降采样到 16kHz Int16 PCM，计算能量做 VAD
 * 每 200ms 输出一帧 (3200 samples = 6400 bytes)
 */
class WakeProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this._buffer = [];
        this._targetRate = 16000;
        this._ratio = 1; // 实际值在 process 中根据 sampleRate 计算
        this._frameSize = 1600; // 100ms @ 16kHz (更快响应)
        this._threshold = 80; // RMS 能量阈值（降低以提高灵敏度）
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (!input || !input[0]) return true;

        const samples = input[0]; // Float32Array, length=128 typically
        const ratio = sampleRate / this._targetRate;

        // 降采样 + Float32 → Int16
        for (let i = 0; i < samples.length; i += ratio) {
            const idx = Math.floor(i);
            const val = Math.max(-1, Math.min(1, samples[idx]));
            this._buffer.push(Math.round(val * 32767));
        }

        // 凑满一帧就输出
        while (this._buffer.length >= this._frameSize) {
            const frame = this._buffer.splice(0, this._frameSize);
            const int16 = new Int16Array(frame);

            // RMS 能量
            let sum = 0;
            for (let i = 0; i < int16.length; i++) {
                sum += int16[i] * int16[i];
            }
            const rms = Math.sqrt(sum / int16.length);

            this.port.postMessage({
                audio: int16.buffer,
                rms: rms,
                isSpeech: rms > this._threshold,
            }, [int16.buffer]);
        }

        return true;
    }
}

registerProcessor('wake-processor', WakeProcessor);
