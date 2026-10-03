import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { App } from "../../src/App";
import { server } from "../../src/mocks/server";
import { initialAppState, useAppStore } from "../../src/state/app-store";
import attributions from "../../../contracts/examples/attributions.json";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  window.localStorage.clear();
  useAppStore.setState(initialAppState);
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("Next Clear Look", () => {
  it("opens on the mission decision with honest opportunity and likelihood language", async () => {
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Next geometric opportunity" })).toBeVisible();
    expect(
      screen.getByText("An overpass is a geometric opportunity, not a promised acquisition."),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: "Historical clear-look likelihood" })).toBeVisible();
    expect(screen.getByText("Based on past AOI observations. Not a weather forecast.")).toBeVisible();
    expect(screen.getByText("69%", { exact: true })).toBeVisible();
    expect(screen.getByText("37 km from track", { exact: true })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Recent looks" })).toBeVisible();
    expect(screen.getByTestId("globe-text-alternative")).toHaveTextContent("Sentinel-2C");
  });

  it("offers all five AOI presets and a keyboard path into real globe drawing", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Next geometric opportunity" });
    await user.click(screen.getByTestId("aoi-switcher"));
    const picker = screen.getByTestId("aoi-picker");
    expect(within(picker).getAllByTestId("aoi-preset-row")).toHaveLength(5);
    await user.click(within(picker).getByRole("tab", { name: "Draw" }));
    await user.click(within(picker).getByRole("button", { name: "Start polygon" }));
    const drawPanel = screen.getByTestId("aoi-draw-panel");
    expect(screen.getByTestId("aoi-draw-map")).toHaveAccessibleName("Draw an area directly on the 3D globe");
    await user.type(within(drawPanel).getByLabelText("Latitude"), "91");
    await user.type(within(drawPanel).getByLabelText("Longitude"), "103.7");
    await user.click(within(drawPanel).getByRole("button", { name: "Add coordinate" }));
    expect(within(drawPanel).getByText(/latitude from −90 to 90/)).toBeVisible();
  });

  it("keeps AOI accounting separate from catalogue context in detail", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Open AOI detail" }));
    expect(screen.getByTestId("aoi-detail")).toBeVisible();
    expect(screen.getByRole("heading", { name: "AOI clear accounting" })).toBeVisible();
    for (const label of [
      "Clear surface",
      "Unclassified",
      "Dark area",
      "Cloud",
      "Thin cirrus",
      "Cloud shadow",
      "Snow or ice",
      "No data",
    ]) {
      expect(screen.getByText(label, { exact: true })).toBeVisible();
    }
    expect(screen.getByRole("heading", { name: "Catalogue context" })).toBeVisible();
    expect(screen.getByText(/full Sentinel-2 tile, not this AOI/)).toBeVisible();
  });

  it("closes evidence with Escape and restores focus to its opener", async () => {
    const user = userEvent.setup();
    render(<App />);
    const opener = await screen.findByRole("button", { name: "Open evidence" });
    await user.click(opener);
    expect(screen.getByRole("dialog", { name: "Evidence and provenance" })).toBeVisible();
    for (const list of screen
      .getByRole("dialog", { name: "Evidence and provenance" })
      .querySelectorAll("dl")) {
      expect([...list.children].every((child) => child.tagName === "DT" || child.tagName === "DD")).toBe(
        true,
      );
    }
    expect(screen.getByRole("heading", { name: "Orbit inputs" })).toBeVisible();
    expect(screen.getByTestId("provenance-graph")).toHaveTextContent("CelesTrak Sentinel OMM catalogue");
    expect(screen.getByTestId("attribution-list")).toHaveTextContent(attributions.data[0].display_text);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Evidence and provenance" })).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});
