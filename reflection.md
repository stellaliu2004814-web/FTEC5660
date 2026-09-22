# Reflection: What OpenAI's Agents API Made Me Realize

**Course:** Agentic AI for Business and FinTech (SEEM5660)
**Date:** September 21, 2026

---

On September 10, OpenAI released the Agents API in public beta. I almost scrolled past it — another API launch, another developer tool. But I read one line that stuck with me: "The difficult part of production agents is increasingly everything around the model — state, tools, retries, observability, and safe execution."

Three hours before I read that, I was sitting in front of my homework with a broken chain.

## What Happened in My Homework

I was building a LangChain pipeline to read supermarket receipts. Send receipt images to DeepSeek's vision model, extract some numbers, add them up. I thought the hard part would be getting the model to read receipts correctly. That was the easy part.

The hard part was everything else. I tried `with_structured_output` to force clean data. It crashed — DeepSeek's thinking mode doesn't support `tool_choice`. So I switched to a prompt-based JSON approach. That worked, but the model kept missing discount lines. Receipt 2 was off by a dollar. Receipt 7 was off by eleven. I rewrote the prompt three times, added a `discount_lines` field so the model would list every discount before summing them, and wrote fallback parsing for when the response came back wrapped in code fences.

When I finally got both answers right — HK$1974.30 and HK$2348.20 — something bothered me. The model didn't change between my failing and passing attempts. Same model, same temperature, same images. What changed was the stuff around it: the prompt, the parsing, the error handling, the self-checking. The chain. The harness.

Then I read OpenAI's announcement, and they were saying the same thing. The model is a component. The harness is the product.

## Why This Bothered Me

I've been treating AI as a tool I'll use at work — like Excel, or Python. Learn the tool, apply it, move on. My plan was: graduate, get a job at a bank or FinTech startup, use AI to do my work faster.

But if OpenAI is turning the orchestration layer into a managed API, then "person who knows how to call models" isn't a career. It's a task — and it's a task being automated right now. The question isn't whether I'll use AI at work. I will. The question is whether I'll be the person building the system, or the person the system replaces.

Models aren't going to replace FinTech professionals next year. But the direction is clear: value is moving from "I can call the API" to "I can design the system that calls the API reliably, safely, and produces auditable results." The first skill is becoming a commodity. The second isn't.

## The Homework Was the Lesson

The thing that hit me: my homework was, in a small way, exactly what OpenAI just productized. I didn't just call a model. I managed state across seven receipts. I ran them in parallel with `batch()`. I handled a failure mode where the thinking mode broke structured output and pivoted to a different approach. I wrote fallback JSON parsing. I added a self-auditing field so the model would list every discount before summing. I debugged why receipt 2 was short a dollar and receipt 7 was short eleven.

None of that is "using AI." All of that is building the system around AI. I didn't realize that's what I was doing until I read the Agents API announcement and recognized the pattern.

## What Changes

A few things shifted for me.

I'm going to stop treating LangChain as a convenience wrapper. It's the layer where production value gets created. The chain I built — parallel processing, error handling, self-auditing prompt — is a small version of what companies pay people to build. That's not homework. That's practice.

I want to get better at the unglamorous parts. Error handling. Observability. Failure analysis. When receipt 2 was off by a dollar, I had to dig in and figure out it was a missed discount line. That kind of debugging — "why did the chain produce the wrong answer, and where exactly did it go wrong?" — is the work that decides whether an AI system can be trusted in production.

And I'm reconsidering what "FinTech + AI" means as a career. I used to think it meant working in finance and using AI tools. Now I think it might mean building the AI systems that financial institutions rely on. The first job is getting automated. The second one is just getting started.
