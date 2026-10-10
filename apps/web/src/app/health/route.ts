import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "healthy",
    service: "ProofFlow Web",
    timestamp: new Date().toISOString(),
  });
}
