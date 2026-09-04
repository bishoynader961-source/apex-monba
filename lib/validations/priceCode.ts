import { z } from 'zod';

export const priceCodeSchema = z.object({
  code: z.string().min(1, 'Code is required').max(20, 'Code too long'),
  description: z.string().min(1, 'Description is required'),
  price: z.string().default('0.00'),
  price_level: z.string().default('AWP'),
  cost_factor_pct: z.string().default('100'),
  markup_pct: z.string().default('0.00'),
  dispensing_fee: z.string().default('0.00'),
  min_price: z.string().default('0.00'),
  max_price: z.string().default('999999.99'),
});

export type PriceCodeForm = z.infer<typeof priceCodeSchema>;
