# Pharmacy Suite - Unified Design System

## 1. Core Philosophy
The Pharmacy Suite interface must prioritize clarity, readability, and modern aesthetics suitable for long hours of operation. It relies on a "Glassmorphism & Dark Mode First" philosophy, using a deep space background contrasted with vibrant, glowing accent colors to demarcate operational zones.

## 2. Color Palette & Tailwind Tokens

### Backgrounds & Surfaces
- **App Background**: `bg-[#0a0a1a]` (Deep Space Black/Blue)
- **Sidebar/Navigation**: `bg-[#0d0d20]`
- **Card Surfaces**: `bg-[#1a1a2e]` with borders `border-gray-800`
- **Hover States**: `hover:bg-gray-800/50` or `hover:bg-[#2a2a3e]`

### Accent Colors (Zone Designation)
- **Point of Sale (Green)**: `bg-green-600` / `text-green-500`
- **Inventory (Blue)**: `bg-blue-600` / `text-blue-500`
- **Patients (Purple)**: `bg-purple-600` / `text-purple-500`
- **Analytics (Orange)**: `bg-orange-600` / `text-orange-500`
- **Destructive/Warnings (Red)**: `bg-red-600` / `text-red-500`

### Typography Colors
- **Primary Text**: `text-gray-100` (Headers, main content)
- **Secondary Text**: `text-gray-400` (Descriptions, subtitles)
- **Muted Text**: `text-gray-500` (Disabled states, placeholders)

## 3. Typography & Spacing
- **Font Family**: Inter (or system sans-serif `font-sans`).
- **Headings**: `text-2xl font-bold tracking-tight`
- **Standard Spacing**:
  - `p-6` for standard card padding.
  - `gap-4` for standard flex/grid gaps.
  - `p-4` for modal/panel padding.

## 4. Components

### Standard Buttons
```tsx
// Primary Action (e.g., Checkout, Save)
className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors"

// Secondary Action (e.g., Cancel, Close)
className="px-4 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md transition-colors"
```

### Cards & Panels
```tsx
className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-6 shadow-xl"
```

### Inputs & Forms
```tsx
className="w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
```

## 5. Implementation Rules
- **No Inline Styles**: Always use Tailwind utility classes.
- **Dark Mode**: Do not use `dark:` prefix variants because the application is exclusively dark mode.
- **Responsiveness**: Use standard breakpoints (`sm:`, `md:`, `lg:`, `xl:`) for flex-to-grid reflowing.
