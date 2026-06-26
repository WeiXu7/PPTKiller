# Radiology Case-Driven Mode

## Product conclusion

PPTKiller should support a radiology case-driven presentation mode. The goal is not to generate a generic deck from a topic, but to help a radiologist organize a teachable case discussion.

The core user need is:

> Turn a clinical imaging topic and a set of available cases into a clear, credible, teachable presentation.

This mode should treat the PPT as the final artifact. Before generating slides, the product should help the user decide what cases are needed, what case information is missing, and how the cases should be sequenced for teaching.

## Two entry paths

### 1. Topic only

When the user only provides a topic, such as lung nodule imaging diagnosis or MRI differential diagnosis of liver lesions, the system should not immediately produce a full deck.

It should first generate a case collection plan:

- What case types are needed for this topic.
- Which cases are essential and which are optional.
- What information should be collected for each case.
- How many cases are recommended for a useful presentation.
- What teaching roles those cases should play.

Example case roles:

- Typical case.
- Atypical case.
- Differential diagnosis case.
- Misdiagnosis or pitfall case.
- Follow-up or pathology-confirmed case.
- Summary or contrast case.

The value in this path is helping the doctor prepare the right material before writing slides.

### 2. Topic plus uploaded cases

When the user provides both a topic and existing imaging cases, the system should first perform case triage instead of directly generating slides.

The intermediate output should be a case inventory:

- What materials exist for each case.
- What teaching value each case appears to have.
- What information is missing.
- Whether the case is ready for presentation.
- Where the case should fit in the teaching storyline.

The system should ask the user to complete missing information instead of inventing it.

## Required case card

Each case should be represented as a structured case card:

- Case ID.
- Age and sex, if provided and properly de-identified.
- Clinical background or chief complaint.
- Imaging modality and protocol, such as CT, MRI, ultrasound, plain scan, enhanced scan, sequence, window, or phase.
- Key images or key image groups.
- Imaging findings, including location, morphology, boundary, density or signal, enhancement pattern, surrounding changes, and interval changes.
- Final diagnosis, pathology, follow-up result, or clinical outcome.
- Teaching role, such as typical, atypical, differential, pitfall, follow-up, or summary.
- Display mode, such as reveal-answer-later, direct explanation, or side-by-side comparison.
- Missing information that needs user confirmation.

## Readiness principle

Before PPT generation, the system should calculate a case readiness state:

- Ready to generate: cases are sufficiently complete and the teaching storyline is clear.
- Can generate with warnings: the deck can be created, but some cases have weak evidence or missing details.
- Not recommended to generate: key information is missing, such as final diagnosis, key images, case context, or de-identification status.

This avoids low-quality decks whose root problem is insufficient or poorly organized source material.

## Suggested workflow

1. Identify the teaching topic.
2. Classify the imaging teaching task, such as sign recognition, differential diagnosis, case review, protocol explanation, reporting standard, rare disease teaching, or misdiagnosis analysis.
3. Generate the expected case collection checklist.
4. Compare uploaded cases against the checklist.
5. Build structured case cards.
6. Ask the user to complete missing information.
7. Sequence cases into a teaching storyline.
8. Generate the final case-driven deck.

## Deck structure

A typical generated deck should follow this structure:

- Title.
- Why this topic matters.
- Case collection overview.
- Diagnostic framework.
- Case 1: typical presentation.
- Case 2: atypical presentation.
- Case 3: differential diagnosis.
- Case 4: pitfall or misdiagnosis risk.
- Case 5: follow-up, pathology, or outcome validation.
- Cross-case comparison.
- Imaging diagnosis checklist.
- Reporting suggestions.
- Discussion questions.
- Summary.
- References or guidelines.

## Product boundaries

This mode should be positioned as a tool for organizing radiology teaching and case discussion materials. It should not present itself as an automatic diagnosis system.

The system may:

- Extract and structure user-provided case information.
- Generate teaching questions.
- Suggest a case sequence.
- Mark missing information.
- Produce draft descriptions for user review.

The system must not:

- Invent patient facts.
- Claim a diagnosis without user-provided support.
- Replace clinical judgment.
- Hide missing information behind confident language.

## MVP scope

The first implementation should focus on case material organization, not automatic DICOM diagnosis or image annotation.

MVP capabilities:

- Topic input.
- Optional case upload.
- Case collection checklist generation.
- Case card creation.
- Missing information detection.
- User confirmation before deck generation.
- Case storyline generation.
- Case-driven PPT generation.

