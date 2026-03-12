import type {
  DiscoverRequest,
  PersonProfile,
  PersonSource,
  PersonSummary,
  JobSummary,
  CostStats,
} from "@/lib/types";

describe("Type contracts", () => {
  it("DiscoverRequest has required fields", () => {
    const req: DiscoverRequest = {
      name: "Test Person",
      company: "TestCo",
      role: "Engineer",
      location: "NYC",
      linkedin_url: "",
      twitter_handle: "",
      github_username: "",
      context: "",
    };
    expect(req.name).toBe("Test Person");
  });

  it("PersonProfile has all expected fields", () => {
    const profile: PersonProfile = {
      id: "123",
      name: "Test",
      current_role: "CTO",
      company: "Co",
      location: "SF",
      bio: "A bio",
      confidence_score: 0.95,
      reputation_score: 0.8,
      key_facts: ["Fact 1"],
      career_timeline: [],
      social_links: {},
      sources: [],
      jobs: [],
      created_at: "2024-01-01",
      updated_at: "2024-01-02",
      status: "active",
      version: 1,
    };
    expect(profile.confidence_score).toBe(0.95);
  });

  it("PersonSource includes confidence field", () => {
    const source: PersonSource = {
      platform: "linkedin",
      url: "https://linkedin.com/in/test",
      title: "Test Profile",
      relevance_score: 0.9,
      source_reliability: 0.85,
      confidence: 0.9,
    };
    expect(source.confidence).toBe(0.9);
  });

  it("JobSummary has status and cost fields", () => {
    const job: JobSummary = {
      id: "j1",
      status: "completed",
      total_cost: 0.015,
      sources_hit: 12,
      cache_hits: 3,
      created_at: "2024-01-01",
      completed_at: "2024-01-01",
    };
    expect(job.status).toBe("completed");
    expect(job.total_cost).toBe(0.015);
  });

  it("PersonSummary has sources_count", () => {
    const p: PersonSummary = {
      id: "p1",
      name: "Jane",
      confidence_score: 0.9,
      status: "active",
      sources_count: 15,
      created_at: "2024-01-01",
      updated_at: "2024-01-02",
    };
    expect(p.sources_count).toBe(15);
  });

  it("CostStats has recent_jobs array", () => {
    const stats: CostStats = {
      total_spend: 1.5,
      total_jobs: 10,
      average_cost: 0.15,
      recent_jobs: [
        {
          id: "j1",
          total_cost: 0.02,
          latency_ms: 5000,
          sources_hit: 8,
          cache_hits: 2,
          created_at: "2024-01-01",
        },
      ],
    };
    expect(stats.recent_jobs).toHaveLength(1);
    expect(stats.average_cost).toBe(0.15);
  });
});
