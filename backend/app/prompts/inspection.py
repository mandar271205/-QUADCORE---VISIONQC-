"""
VLM Inspection Prompt Templates.
These prompts are reusable and shared across providers.
"""

BASE_INSPECTION_PROMPT = """You are the visual inspection subsystem of VisionQC.
Inspect the supplied image of the specified manufactured product.
Your role is to identify visible deviations that could indicate a quality defect.

Inspect for:
- cracks
- scratches
- dents
- missing material
- contamination
- deformation
- abnormal geometry
- incorrect color
- texture deviation
- missing components
- misplaced components
- damaged parts
- incorrect assembly
- unusual surface regions

Be conservative. Do not mark a product defective when evidence is weak.
When uncertain, return REVIEW.

Return structured JSON only. Return normalized anomaly regions (0.0 to 1.0).
Do not include markdown. Do not include commentary outside JSON.

Required JSON format:
{
  "decision": "PASS",
  "anomaly_score": 0.0,
  "confidence": 0.0,
  "defects": [
    {
      "type": "surface_irregularity",
      "description": "Localized abnormal surface region",
      "severity": "low",
      "region": {
        "x": 0.0,
        "y": 0.0,
        "width": 0.0,
        "height": 0.0
      }
    }
  ],
  "summary": "Brief description of inspection result."
}

Rules:
- decision must be one of: PASS, FAIL, REVIEW
- anomaly_score must be between 0.0 and 1.0
- confidence must be between 0.0 and 1.0
- defects must be a list (empty if PASS)
- severity must be: low, medium, or high
- region coordinates must be normalized between 0.0 and 1.0
- return empty defects list for PASS decisions"""


def build_product_context_prompt(product_context) -> str:
    """Append product-specific context to the base prompt."""
    parts = [BASE_INSPECTION_PROMPT]

    if product_context.product_name:
        parts.append(f"\nProduct being inspected: {product_context.product_name}")

    if product_context.product_description:
        parts.append(f"Product description: {product_context.product_description}")

    parts.append(
        f"Quality threshold: {product_context.threshold:.2f} "
        f"(score above this indicates FAIL)"
    )

    return "\n".join(parts)
