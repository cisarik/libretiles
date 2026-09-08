"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { ReplayStudio } from "@/components/admin/ReplayStudio";

function ReplayRoute() { const params = useParams<{ id: string }>(); return <ReplayStudio gameId={params.id} />; }
export default function ReplayPage() { return <Suspense fallback={<div className="p-8">Loading replay route...</div>}><ReplayRoute /></Suspense>; }
