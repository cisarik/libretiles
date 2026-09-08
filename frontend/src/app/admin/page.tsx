import { Suspense } from "react";
import { AdminGamesList } from "@/components/admin/AdminGamesList";
export default function AdminPage() { return <Suspense fallback={<div className="p-8">Loading games...</div>}><AdminGamesList /></Suspense>; }
