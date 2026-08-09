import { R2 } from "@convex-dev/r2";
import { components } from "./_generated/api";

// Cloudflare R2 via the official Convex component. Configure with:
//   npx convex env set R2_ENDPOINT https://<account-id>.r2.cloudflarestorage.com
//   npx convex env set R2_ACCESS_KEY_ID ...
//   npx convex env set R2_SECRET_ACCESS_KEY ...
//   npx convex env set R2_BUCKET presenton-artifacts
export const r2 = new R2(components.r2);
