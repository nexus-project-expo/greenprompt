# Project brief: NEXUS 2026 Student Project Expo

## Event

- **Event:** NEXUS 2026, CSI Student Summit on Innovation & Technology, hosted by CSI Student Branch, NMAMIT, Nitte.
- **Exhibition date:** 25 November 2026, NMAMIT, Nitte. Project Expo slot: 2:00 to 4:00 PM (per brochure schedule).
- **Website:** https://nexus.csinmamit.in (Project Expo page: /expo)
- **Theme (all categories must fit it):** "Technology for a Sustainable and Smarter Future"
- **Our category:** Energy & Resource Management
- **Abstract deadline:** extended to 23 November 2026 (organisers' WhatsApp announcement and website).
- **Team size rule:** 2 to 5 students. We are 3.
- **Prize pool:** Rs 25,000. Winner 10,000; 1st runner-up 6,000; 2nd runner-up 4,000; Best Innovation 2,500; Best Real-World Impact 2,500.

## Presentation format (conflicting sources, plan for the shorter one)

- Brochure PDF: 7 min presentation and demo + 3 min jury Q&A.
- Website (newer): 5 min presentation and demo + 5 min jury Q&A.
- **Plan a 5-minute demo and prepare for 5 minutes of questions.**

## Judging rubric (from the brochure)

| Criterion | Weight |
|---|---|
| Relevance of the problem | 15% |
| Innovation and originality | 20% |
| Strength of technical implementation | 20% |
| Functions as intended | 20% |
| Feasibility for real-world implementation | 10% |
| Clarity of presentation | 10% |
| Scalability and real-world impact | 5% |

40% depends on a working build. That is why reliability is rule #1 in `CLAUDE.md`.

## Exhibition guidelines

- Teams bring their own hardware, devices and accessories (we bring the laptop; check for a power socket and do not rely on venue Wi-Fi).
- A working demonstration is strongly encouraged.
- **Every team member must understand the whole project and explain their own contribution.** Keep the code readable enough that all three of us can explain any module.
- Special infrastructure requirements must be communicated to organisers in advance.

## Likely jury / panel (from the brochure's industry panel; jury not officially confirmed)

- **Mr. Aditya R. Poonja**, Business Development Executive, AIC Nitte. Background in AI, robotics, computer vision, embedded systems (Bosch, Fraunhofer IOSB). Teammate reports he has judged before, asks many questions, and is tired of food-waste projects. Expect hard technical questions on measurement and accuracy.
- **Dr. Shashank Shetty**, Associate Professor, CSE, NMAMIT. Startup mentor, patents, research publications. Expect questions on novelty and prior work.
- **Mr. Sujith Kumar**, Solutions Architect, Niveus Solutions. Cloud architecture (GCP, AWS, Azure). Expect questions on cloud cost, scale and deployment.

## What we submitted (abstract summary; full PDF in docs/abstract.pdf)

- **Team name:** Team Undervolt
- **Title:** GreenPrompt: carbon aware routing for everyday AI use
- **Problem:** People use large AI models for trivial tasks. IEA *Energy and AI* (2025) projects data centre electricity rising from about 415 TWh (2024) to about 945 TWh (2030), with AI the main driver. Google measured a median Gemini text prompt at about 0.24 Wh and 0.26 mL water (arXiv:2508.15734, 2025). Many prompts don't need a large model, many repeat, and users can't see the cost.
- **Solution:** semantic cache, difficulty router with escalation (small efficient model vs large model), carbon receipt and dashboard, CO2 from India's CEA grid emission factor, optional deferral of non-urgent batch jobs to cleaner grid hours, ~100-question evaluation reporting energy saved alongside quality retained.
- **Prior work we acknowledge:** RouteLLM (LMSYS 2024, arXiv:2406.18665) routes between strong and weak models to save cost. Our difference: we optimise for energy and emissions and show the cost to the user per answer.

## Positioning (say this, in this order)

1. Everyone does "AI for sustainability". We do sustainability *for* AI.
2. Fits both halves of the theme: smarter (picks the right model per prompt) and sustainable (cuts energy, CO2, water).
3. No new hardware. Plugs in front of AI tools an institution already uses.
4. We measured what we could, labelled what we estimated, and we show the quality trade-off honestly.
