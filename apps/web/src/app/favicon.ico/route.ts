export function GET() {
  return new Response(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
      <rect width="64" height="64" rx="10" fill="#0c0f11"/>
      <path d="M16 42V22l16-8 16 8v20l-16 8-16-8Z" fill="none" stroke="#45d483" stroke-width="4" stroke-linejoin="round"/>
      <path d="M24 32h16" stroke="#edf2f4" stroke-width="4" stroke-linecap="round"/>
    </svg>`,
    {
      headers: {
        "content-type": "image/svg+xml",
        "cache-control": "public, max-age=86400",
      },
    },
  );
}
