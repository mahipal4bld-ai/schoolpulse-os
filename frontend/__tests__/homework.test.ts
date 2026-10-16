import { privateFileUrl, session } from "@/src/api";

describe("privateFileUrl", () => {
  it("adds the access token as a query param for private files", () => {
    session.setToken("abc.def");
    expect(privateFileUrl("f1")).toMatch(/\/api\/files\/f1\?token=abc\.def$/);
    session.setToken(null);
    expect(privateFileUrl("f1")).toMatch(/\/api\/files\/f1$/);
  });
});
