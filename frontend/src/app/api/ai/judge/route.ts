/**
 * AI Word Judge API Route (Tier 3 validation)
 *
 * Used as a fallback when a word is not in the local Collins 2019 dictionary.
 * The AI acts as a Scrabble referee, judging whether words are valid
 * based on lexicon knowledge and natural language understanding.
 *
 * Validation pipeline:
 *   Tier 1: Local Collins 2019 dictionary (279,496 words, O(1) lookup) — Django
 *   Tier 2: Online dictionary API (optional) — Django
 *   Tier 3: AI Judge (this route) — Vercel AI Gateway
 *
 * See: scrabgpt/ai/client.py build_judge_prompt() for the original desktop version.
 */

import { NextRequest, NextResponse } from "next/server";
import { generateText } from "ai";
import { getModel } from "@/lib/ai-gateway";
import { JUDGE_SYSTEM_PROMPT } from "@/lib/prompts";

export async function POST(req: NextRequest) {
  try {
    const { words, model_id } = (await req.json()) as {
      words: string[];
      model_id?: string;
    };

    if (!words || words.length === 0) {
      return NextResponse.json(
        { error: "No words provided" },
        { status: 400 },
      );
    }

    const model = getModel(model_id);

    const result = await generateText({
      model,
      maxOutputTokens: 1000,
      temperature: 0.1,
      system: JUDGE_SYSTEM_PROMPT,
      prompt: `Validate these words for English Scrabble play: ${words.join(", ")}. Return JSON exactly matching the schema.`,
    });

    try {
      const jsonMatch = result.text.match(/\{[\s\S]*"results"[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        return NextResponse.json({
          ...parsed,
          model: model_id || process.env.NEXT_PUBLIC_DEFAULT_MODEL,
          usage: result.usage,
        });
      }
    } catch {
      // JSON parse failed
    }

    return NextResponse.json({
      results: words.map((w) => ({
        word: w,
        valid: false,
        reason: "Could not determine validity",
      })),
    });
  } catch (error) {
    console.error("AI judge error:", error);
    return NextResponse.json(
      { error: "AI judge failed" },
      { status: 500 },
    );
  }
}
