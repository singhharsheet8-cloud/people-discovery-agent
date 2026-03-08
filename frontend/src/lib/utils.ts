import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function platformIcon(platform: string): string {
  const icons: Record<string, string> = {
    linkedin: "Linkedin",
    youtube: "Youtube",
    twitter: "Twitter",
    github: "Github",
    academic: "GraduationCap",
    news: "Newspaper",
    web: "Globe",
  };
  return icons[platform] || "Globe";
}

export function confidenceLabel(score: number): string {
  if (score >= 0.85) return "Very High";
  if (score >= 0.7) return "High";
  if (score >= 0.5) return "Moderate";
  if (score >= 0.3) return "Low";
  return "Very Low";
}

export function confidenceColor(score: number): string {
  if (score >= 0.85) return "text-emerald-400";
  if (score >= 0.7) return "text-green-400";
  if (score >= 0.5) return "text-yellow-400";
  if (score >= 0.3) return "text-orange-400";
  return "text-red-400";
}
