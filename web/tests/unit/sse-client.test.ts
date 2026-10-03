import { describe, expect, it, vi } from "vitest";
import { buildResumeUrl, decodeSseEvent, shouldAcceptEvent, SseClient } from "../../src/api/sse-client";

const progress = JSON.stringify({
  id: "job_demo:7",
  sequence: 7,
  type: "job.progress",
  stream: "job",
  job_id: "job_demo",
  emitted_at: "2026-10-03T04:00:00Z",
  mode: "replay",
  clock_time: "2026-10-03T04:00:00Z",
  schema_version: "1.0",
  data: { stage: "raster", stage_progress: 0.5, overall_progress: 0.7 },
});

describe("SSE client", () => {
  it("decodes the contract envelope and ignores heartbeats", () => {
    expect(
      decodeSseEvent(`: heartbeat\n\nid: job_demo:7\nevent: job.progress\ndata: ${progress}\n\n`),
    ).toMatchObject({
      id: "job_demo:7",
      type: "job.progress",
      schema_version: "1.0",
    });
    expect(decodeSseEvent(": heartbeat 2026-10-03T04:00:00Z\n\n")).toBeNull();
  });

  it("deduplicates IDs and rejects incompatible known schemas", () => {
    const seen = new Set<string>();
    const event = decodeSseEvent(`data: ${progress}\n\n`);
    expect(event && shouldAcceptEvent(event, seen)).toBe(true);
    expect(event && shouldAcceptEvent(event, seen)).toBe(false);
    expect(event && shouldAcceptEvent({ ...event, id: "job_demo:8", schema_version: "2.0" }, seen)).toBe(
      false,
    );
  });

  it("adds the browser-compatible resume cursor on reconnect", () => {
    expect(buildResumeUrl("/v1/events", "live:42")).toBe("/v1/events?last_event_id=live%3A42");
    expect(buildResumeUrl("/v1/events?scope=all", "live:42")).toBe(
      "/v1/events?scope=all&last_event_id=live%3A42",
    );
  });

  it("reconnects after EOF with the last accepted event ID", async () => {
    const urls: string[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      urls.push(input instanceof Request ? input.url : input instanceof URL ? input.href : input);
      if (urls.length === 1) {
        return new Response(`event: job.progress\ndata: ${progress}\n\n`, {
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      return await new Promise<Response>((resolve) => {
        window.setTimeout(() => resolve(new Response(null, { status: 204 })), 100);
      });
    }) as typeof fetch;
    const client = new SseClient({
      url: "/v1/events",
      fetcher,
      reconnectDelayMs: 0,
      onEvent: () => undefined,
    });
    client.start();
    await vi.waitFor(() => expect(urls).toHaveLength(2));
    expect(urls[1]).toBe("/v1/events?last_event_id=job_demo%3A7");
    client.stop();
  });
});
