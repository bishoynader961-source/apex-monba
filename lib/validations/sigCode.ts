import { z } from 'zod';

export const sigCodeSchema = z.object({
  code: z.string().min(1, 'Code is required').max(20, 'Code too long'),
  full_text: z.string().min(1, 'Description is required'),
  language: z.enum(['EN', 'ES']).default('EN'),
  days_accumulated: z.string().optional().or(z.literal('')),
  offset: z.number().int().min(0, 'Offset must be non-negative').default(0),
});

export type SigCodeForm = z.infer<typeof sigCodeSchema>;
