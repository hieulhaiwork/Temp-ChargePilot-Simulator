import { AuthGate } from "@/components/auth/AuthGate";
import { RoleShell } from "@/components/system/RoleShell";

export default function OperatorLayout({ children }: LayoutProps<"/operator">) {
  return (
    <AuthGate role="operator">
      <RoleShell role="operator">{children}</RoleShell>
    </AuthGate>
  );
}
