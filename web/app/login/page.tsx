import { signupMode } from "@/lib/env";
import { LoginForm } from "./login-form";

export const dynamic = "force-dynamic";

/**
 * Server component. `signupMode` is read here, on the server, and the single
 * derived boolean is passed down — the mode itself never reaches the browser.
 */
export default function LoginPage() {
  return <LoginForm signupEnabled={signupMode() !== "closed"} />;
}
