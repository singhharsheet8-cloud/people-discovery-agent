import { healthCheck } from "@/lib/api";

const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
  localStorage.clear();
});

describe("fetchApi", () => {
  it("healthCheck calls /api/health and returns data", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: "healthy" }),
    });

    const data = await healthCheck();
    expect(data).toEqual({ status: "healthy" });
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/health"),
      expect.objectContaining({
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      })
    );
  });

  it("throws on non-ok response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => ({ message: "Something went wrong" }),
    });

    await expect(healthCheck()).rejects.toThrow("Something went wrong");
  });

  it("includes Authorization header when token is stored", async () => {
    localStorage.setItem("access_token", "test-jwt-token");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: "healthy" }),
    });

    await healthCheck();
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-jwt-token",
        }),
      })
    );
  });
});

describe("loginAdmin", () => {
  it("stores tokens on successful login", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: "at-123",
        refresh_token: "rt-456",
        expires_in: 1800,
        token_type: "bearer",
        email: "admin@test.com",
        role: "admin",
      }),
    });

    const { loginAdmin } = await import("@/lib/api");
    await loginAdmin("admin@test.com", "pass");

    expect(localStorage.getItem("access_token")).toBe("at-123");
    expect(localStorage.getItem("refresh_token")).toBe("rt-456");
  });
});
