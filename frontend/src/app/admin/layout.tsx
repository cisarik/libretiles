import Link from "next/link";
import { AdminAccessGate } from "@/components/admin/AdminAccessGate";
import styles from "@/components/admin/admin.module.css";

export default function AdminLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <div className={styles.adminRoot}><AdminAccessGate><div className={styles.shell}><nav className={styles.nav} aria-label="Admin navigation"><Link href="/admin">Games List</Link><span title="Open a game from the list">Replay Studio</span><Link href="/admin/playground">Playground (Preview)</Link><Link href="/admin/analytics">Analytics (Preview)</Link><Link className={styles.back} href="/play">← Back to Game</Link></nav>{children}</div></AdminAccessGate></div>;
}
