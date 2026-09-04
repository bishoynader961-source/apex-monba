import { z } from 'zod';

export const patientGeneralSchema = z.object({
  last_name: z.string().min(1, 'Last name is required'),
  first_name: z.string().min(1, 'First name is required'),
  middle_initial: z.string().max(1, 'Middle initial must be a single character').optional().or(z.literal('')),
  dob: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Invalid date format (YYYY-MM-DD)'),
  ssn: z.string().regex(/^\d{3}-?\d{2}-?\d{4}$/, 'Invalid SSN format').optional().or(z.literal('')),
  sex: z.enum(['M', 'F', 'O']).optional(),
  address: z.string().min(1, 'Address is required'),
  city: z.string().min(1, 'City is required'),
  state: z.string().length(2, 'State must be 2 characters').optional().or(z.literal('')),
  zip: z.string().regex(/^\d{5}(-\d{4})?$/, 'Invalid ZIP code').optional().or(z.literal('')),
  home_phone: z.string().regex(/^\d{3}-?\d{3}-?\d{4}$/, 'Invalid phone format').optional().or(z.literal('')),
  cell_phone: z.string().regex(/^\d{3}-?\d{3}-?\d{4}$/, 'Invalid phone format').optional().or(z.literal('')),
  email: z.string().email('Invalid email format').optional().or(z.literal('')),
  primary_care_physician: z.string().optional(),
  driver_license: z.string().optional(),
  employer_id: z.string().optional(),
  contact_phone: z.string().optional(),
  insurance_provider: z.string().optional(),
  policy_number: z.string().optional(),
  group_number: z.string().optional(),
  patient_allergies: z.string().optional(),
  comments: z.string().optional(),
});

export type PatientGeneralForm = z.infer<typeof patientGeneralSchema>;