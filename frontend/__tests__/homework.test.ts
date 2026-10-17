import { grantUrl } from "@/src/api";

const read = (f: string) => require("fs").readFileSync(require("path").join(__dirname, "..", f), "utf8");

describe("secure downloads", () => {
  it("builds grant URLs from server paths without any access token", () => {
    expect(grantUrl("/api/downloads/abc")).toMatch(/\/api\/downloads\/abc$/);
    expect(grantUrl("/api/downloads/abc")).not.toMatch(/token=/);
  });

  it("never puts access tokens into URLs anywhere in the app", () => {
    for (const f of ["src/api.ts", "src/utils/download.ts", "src/components/homework.tsx", "src/components/exams.tsx"]) {
      expect(read(f)).not.toMatch(/[?&]token=/);
    }
  });
});
