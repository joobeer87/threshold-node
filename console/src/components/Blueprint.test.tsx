import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Blueprint } from "./Blueprint";

describe("Blueprint", () => {
  it("wraps and clips long outdoor no-go labels inside a narrow zone", () => {
    const { container } = render(<Blueprint zones={[{
      id: "garden",
      name: "Vegetable Garden",
      access: "no-go",
      boundary: [300, 200, 100, 120],
      outdoor: true,
    }]} />);

    const name = container.querySelector(".zone-name");
    const state = container.querySelector(".zone-state");
    expect(Array.from(name?.querySelectorAll("tspan") ?? []).map((line) => line.textContent))
      .toEqual(["Vegetable", "Garden"]);
    expect(Array.from(state?.querySelectorAll("tspan") ?? []).map((line) => line.textContent))
      .toEqual(["OUTDOOR ·", "NO-GO"]);
    expect(name?.getAttribute("clip-path")).toMatch(/^url\(#.+-zone-label-0\)$/);
    expect(state?.getAttribute("clip-path")).toBe(name?.getAttribute("clip-path"));
    expect(container.querySelector(".zone title")).toHaveTextContent(
      "Vegetable Garden — OUTDOOR · NO-GO",
    );
  });

  it("ellipsizes an unbroken visual label while preserving its full title", () => {
    const { container } = render(<Blueprint zones={[{
      id: "synthetic-narrow-zone",
      name: "SyntheticUnbrokenZoneName",
      access: "restricted",
      boundary: [0, 0, 60, 80],
    }]} />);

    expect(container.querySelector(".zone-name tspan")?.textContent).toMatch(/…$/);
    expect(container.querySelector(".zone title")).toHaveTextContent(
      "SyntheticUnbrokenZoneName — RESTRICTED",
    );
    expect(container.querySelector(".zone-name")?.getAttribute("clip-path"))
      .toMatch(/^url\(#.+-zone-label-0\)$/);
  });
});
