/**
 * 音频处理纯函数：重采样、PCM 转换、WAV 编码。
 * 被 useAudioRecorder（一次性 WAV）和 useRealtimeAsr（实时流）共用。
 */

export const TARGET_SAMPLE_RATE = 16000

/** 把多个 Float32 音频块拼接为一个 */
export function mergeChunks(chunks: Float32Array[]): Float32Array {
  let total = 0
  for (const c of chunks) total += c.length
  const out = new Float32Array(total)
  let offset = 0
  for (const c of chunks) {
    out.set(c, offset)
    offset += c.length
  }
  return out
}

/** 线性插值重采样到目标采样率（仅降采样；to >= from 时原样返回） */
export function downsample(buffer: Float32Array, from: number, to: number): Float32Array {
  if (to >= from) return buffer
  const ratio = from / to
  const newLen = Math.round(buffer.length / ratio)
  const result = new Float32Array(newLen)
  for (let i = 0; i < newLen; i++) {
    const idx = i * ratio
    const low = Math.floor(idx)
    const high = Math.min(low + 1, buffer.length - 1)
    const frac = idx - low
    result[i] = buffer[low] * (1 - frac) + buffer[high] * frac
  }
  return result
}

/** Float32 [-1,1] → 16-bit PCM */
export function floatToPcm16(samples: Float32Array): Int16Array {
  const out = new Int16Array(samples.length)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}

/** Float32 PCM → 16-bit 单声道 WAV Blob */
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)

  const writeStr = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i))
  }

  writeStr(0, "RIFF")
  view.setUint32(4, 36 + samples.length * 2, true)
  writeStr(8, "WAVE")
  writeStr(12, "fmt ")
  view.setUint32(16, 16, true) // PCM chunk size
  view.setUint16(20, 1, true) // PCM format
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // byte rate
  view.setUint16(32, 2, true) // block align
  view.setUint16(34, 16, true) // bits per sample
  writeStr(36, "data")
  view.setUint32(40, samples.length * 2, true)

  const pcm = floatToPcm16(samples)
  let offset = 44
  for (let i = 0; i < pcm.length; i++) {
    view.setInt16(offset, pcm[i], true)
    offset += 2
  }

  return new Blob([view], { type: "audio/wav" })
}
