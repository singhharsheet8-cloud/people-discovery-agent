import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ConfidenceScore } from "@/components/confidence-score";
import { SourceCard } from "@/components/source-card";

describe("ConfidenceScore", () => {
  it("renders percentage correctly", () => {
    render(<ConfidenceScore score={0.85} />);
    expect(screen.getByText("85%")).toBeInTheDocument();
  });

  it("renders Very High label for 0.95", () => {
    render(<ConfidenceScore score={0.95} />);
    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(screen.getByText("Very High")).toBeInTheDocument();
  });

  it("renders Low label for 0.35", () => {
    render(<ConfidenceScore score={0.35} />);
    expect(screen.getByText("35%")).toBeInTheDocument();
    expect(screen.getByText("Low")).toBeInTheDocument();
  });

  it("renders small size variant", () => {
    render(<ConfidenceScore score={0.75} size="sm" />);
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
  });

  it("renders large size variant", () => {
    render(<ConfidenceScore score={0.6} size="lg" />);
    expect(screen.getByText("60%")).toBeInTheDocument();
    expect(screen.getByText("Moderate")).toBeInTheDocument();
  });

  it("handles edge case of 0 score", () => {
    render(<ConfidenceScore score={0} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
    expect(screen.getByText("Very Low")).toBeInTheDocument();
  });

  it("handles edge case of 1.0 score", () => {
    render(<ConfidenceScore score={1.0} />);
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("Very High")).toBeInTheDocument();
  });
});

describe("SourceCard", () => {
  const baseSource = {
    platform: "linkedin",
    url: "https://linkedin.com/in/johndoe",
    title: "John Doe - CTO at Acme",
    relevance_score: 0.92,
  };

  it("renders title and URL", () => {
    render(<SourceCard source={baseSource} />);
    expect(screen.getByText("John Doe - CTO at Acme")).toBeInTheDocument();
    expect(screen.getByText("https://linkedin.com/in/johndoe")).toBeInTheDocument();
  });

  it("renders relevance percentage", () => {
    render(<SourceCard source={baseSource} />);
    expect(screen.getByText("92%")).toBeInTheDocument();
  });

  it("links to the source URL", () => {
    render(<SourceCard source={baseSource} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "https://linkedin.com/in/johndoe");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders raw content when available", () => {
    const withContent = { ...baseSource, raw_content: "Some snippet text here" };
    render(<SourceCard source={withContent} />);
    expect(screen.getByText("Some snippet text here")).toBeInTheDocument();
  });

  it("does not render raw content when null", () => {
    const withNull = { ...baseSource, raw_content: null };
    render(<SourceCard source={withNull} />);
    expect(screen.queryByText("Some snippet")).not.toBeInTheDocument();
  });

  it("handles missing relevance score gracefully", () => {
    const noScore = { platform: "web", url: "https://example.com", title: "Test" } as any;
    render(<SourceCard source={noScore} />);
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("renders different platform icons", () => {
    const github = { ...baseSource, platform: "github", url: "https://github.com/test" };
    const { container } = render(<SourceCard source={github} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});
