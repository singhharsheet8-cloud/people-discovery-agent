import { cn, confidenceLabel, confidenceColor, platformIcon } from "@/lib/utils";

describe("cn", () => {
  it("merges class names", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("handles conditional classes", () => {
    expect(cn("base", false && "hidden", "visible")).toBe("base visible");
  });

  it("deduplicates tailwind classes", () => {
    expect(cn("p-4", "p-8")).toBe("p-8");
  });
});

describe("confidenceLabel", () => {
  it("returns Very High for >= 0.85", () => {
    expect(confidenceLabel(0.95)).toBe("Very High");
    expect(confidenceLabel(0.85)).toBe("Very High");
  });

  it("returns High for >= 0.7", () => {
    expect(confidenceLabel(0.75)).toBe("High");
    expect(confidenceLabel(0.7)).toBe("High");
  });

  it("returns Moderate for >= 0.5", () => {
    expect(confidenceLabel(0.6)).toBe("Moderate");
    expect(confidenceLabel(0.5)).toBe("Moderate");
  });

  it("returns Low for >= 0.3", () => {
    expect(confidenceLabel(0.4)).toBe("Low");
    expect(confidenceLabel(0.3)).toBe("Low");
  });

  it("returns Very Low for < 0.3", () => {
    expect(confidenceLabel(0.1)).toBe("Very Low");
    expect(confidenceLabel(0)).toBe("Very Low");
  });
});

describe("confidenceColor", () => {
  it("returns emerald for high scores", () => {
    expect(confidenceColor(0.9)).toBe("text-emerald-400");
  });

  it("returns green for good scores", () => {
    expect(confidenceColor(0.75)).toBe("text-green-400");
  });

  it("returns yellow for moderate scores", () => {
    expect(confidenceColor(0.55)).toBe("text-yellow-400");
  });

  it("returns orange for low scores", () => {
    expect(confidenceColor(0.35)).toBe("text-orange-400");
  });

  it("returns red for very low scores", () => {
    expect(confidenceColor(0.1)).toBe("text-red-400");
  });
});

describe("platformIcon", () => {
  it("maps known platforms", () => {
    expect(platformIcon("linkedin")).toBe("Linkedin");
    expect(platformIcon("youtube")).toBe("Youtube");
    expect(platformIcon("github")).toBe("Github");
    expect(platformIcon("twitter")).toBe("Twitter");
  });

  it("defaults to Globe for unknown platforms", () => {
    expect(platformIcon("unknown")).toBe("Globe");
    expect(platformIcon("")).toBe("Globe");
  });
});
