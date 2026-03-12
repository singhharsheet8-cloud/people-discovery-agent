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
      created_at: "2024-01-01",
      updated_at: "2024-01-02",
      source_count: 5,
      cost_breakdown: {},
    };
    expect(profile.confidence_score).toBe(0.95);
  });

  it("PersonSource includes confidence field", () => {
    const source: PersonSource = {
      id: "s1",
      source_type: "web",
      platform: "linkedin",
      url: "https://linkedin.com/in/test",
      title: "Test Profile",
      snippet: "snippet",
      relevance_score: 0.9,
      source_reliability: 0.85,
      confidence: 0.9,
      created_at: "2024-01-01",
    };
    expect(source.confidence).toBe(0.9);
  });

  it("JobSummary has status field", () => {
    const job: JobSummary = {
      id: "j1",
      status: "completed",
      input_params: {},
      person_id: "p1",
      error_message: null,
      created_at: "2024-01-01",
      completed_at: "2024-01-01",
    };
    expect(job.status).toBe("completed");
  });

  it("CostStats has cost_by_source", () => {
    const stats: CostStats = {
      total_discoveries: 10,
      total_cost: 1.5,
      cost_by_source: { web: 0.5, llm: 1.0 },
      recent_jobs: [],
    };
    expect(stats.total_cost).toBe(1.5);
  });
});
