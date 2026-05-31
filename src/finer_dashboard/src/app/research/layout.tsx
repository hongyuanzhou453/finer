export default function ResearchLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div className="flex h-full w-full flex-col">{children}</div>;
}
