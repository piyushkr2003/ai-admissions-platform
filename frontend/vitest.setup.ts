import "@testing-library/jest-dom/vitest";

// jsdom's Blob implementation doesn't include arrayBuffer() (every real
// browser's does - it's a standard File API method), which the voice
// console's audio-upload path (features/voice/voice-console.tsx) relies
// on to base64-encode a recorded clip before sending it. Polyfill it via
// FileReader (which jsdom does implement) so tests can exercise that
// path instead of only ever hitting a jsdom-only TypeError.
if (typeof Blob !== "undefined" && !Blob.prototype.arrayBuffer) {
  Blob.prototype.arrayBuffer = function arrayBuffer(): Promise<ArrayBuffer> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as ArrayBuffer);
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(this);
    });
  };
}
