import JobForm from "@/components/JobForm";

export default function HomePage() {
  return (
    <main>
      <h1>
        YouTube video in, <br />
        guitar tab out.
      </h1>
      <p className="lead">
        TabForge downloads the audio, isolates the guitar with AI source separation,
        transcribes every note, and works out where your fingers should go. You get a
        Guitar Pro (.gp) file ready to download.
      </p>

      <div className="card">
        <JobForm />
      </div>
    </main>
  );
}
