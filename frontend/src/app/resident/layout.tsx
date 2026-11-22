import { AuthGate } from "@/components/auth/AuthGate";
import { RoleShell } from "@/components/system/RoleShell";

export default function ResidentLayout({ children }: LayoutProps<"/resident">) {
  return (
    <AuthGate role="resident">
      <RoleShell role="resident">{children}</RoleShell>
    </AuthGate>
  );
}
