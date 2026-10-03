export interface SseEnvelope<T = Record<string, unknown>> {
  id: string;
  sequence: number;
  type: string;
  stream: "job" | "live";
  job_id?: string;
  emitted_at: string;
  mode: "live" | "replay";
  clock_time: string;
  schema_version: string;
  data: T;
}

export function decodeSseEvent(block: string): SseEnvelope | null {
  const dataLines = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (dataLines.length === 0) return null;
  try {
    return JSON.parse(dataLines.join("\n")) as SseEnvelope;
  } catch {
    return null;
  }
}

export function shouldAcceptEvent(event: SseEnvelope, seen: Set<string>): boolean {
  if (event.schema_version !== "1.0" || seen.has(event.id)) return false;
  seen.add(event.id);
  return true;
}

export function buildResumeUrl(url: string, lastEventId?: string): string {
  if (!lastEventId) return url;
  return `${url}${url.includes("?") ? "&" : "?"}last_event_id=${encodeURIComponent(lastEventId)}`;
}

export interface SseClientOptions {
  url: string;
  onEvent: (event: SseEnvelope) => void;
  onStatus?: (status: "connecting" | "open" | "retrying" | "closed") => void;
  fetcher?: typeof fetch;
  reconnectDelayMs?: number;
}

export class SseClient {
  readonly #options: SseClientOptions;
  readonly #seen = new Set<string>();
  #lastEventId: string | undefined;
  #abortController: AbortController | undefined;
  #stopped = true;

  constructor(options: SseClientOptions) {
    this.#options = options;
  }

  start() {
    if (!this.#stopped) return;
    this.#stopped = false;
    void this.#connect();
  }

  stop() {
    this.#stopped = true;
    this.#abortController?.abort();
    this.#options.onStatus?.("closed");
  }

  async #connect() {
    while (!this.#stopped) {
      this.#abortController = new AbortController();
      this.#options.onStatus?.(this.#lastEventId ? "retrying" : "connecting");
      try {
        const response = await (this.#options.fetcher ?? fetch)(
          buildResumeUrl(this.#options.url, this.#lastEventId),
          {
            headers: { Accept: "text/event-stream" },
            signal: this.#abortController.signal,
          },
        );
        if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`);
        this.#options.onStatus?.("open");
        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";
        while (!this.#stopped) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += value;
          let boundary = buffer.search(/\r?\n\r?\n/);
          while (boundary >= 0) {
            const block = buffer.slice(0, boundary);
            const separatorLength = buffer.slice(boundary).startsWith("\r\n\r\n") ? 4 : 2;
            buffer = buffer.slice(boundary + separatorLength);
            const event = decodeSseEvent(block);
            if (event && shouldAcceptEvent(event, this.#seen)) {
              this.#lastEventId = event.id;
              this.#options.onEvent(event);
            }
            boundary = buffer.search(/\r?\n\r?\n/);
          }
        }
      } catch (error) {
        if (this.#stopped || (error instanceof DOMException && error.name === "AbortError")) return;
      }
      if (!this.#stopped) {
        this.#options.onStatus?.("retrying");
        await new Promise((resolve) => window.setTimeout(resolve, this.#options.reconnectDelayMs ?? 1_500));
      }
    }
  }
}
