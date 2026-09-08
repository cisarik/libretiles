import { Suspense } from "react";
import { AdminAccessGate } from "@/components/admin/AdminAccessGate";
import { AdminNavigation } from "@/components/admin/AdminNavigation";
import styles from "@/components/admin/admin.module.css";

export default function AdminLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <div className={styles.adminRoot}><AdminAccessGate><div className={styles.shell}><Suspense fallback={<div className={styles.nav}>Loading console navigation...</div>}><AdminNavigation /></Suspense>{children}</div></AdminAccessGate></div>;
}
