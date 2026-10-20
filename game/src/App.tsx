/**
 * Placeholder shell for Increment 0. Establishes the accessible page
 * structure (skip link, landmarks, single h1) that later screens reuse.
 */
export function App() {
  return (
    <>
      <a class="skip-link" href="#main">
        Skip to main content
      </a>
      <header class="site-header">
        <p class="site-name">AgroEcosystemSim</p>
      </header>
      <main id="main" tabIndex={-1}>
        <h1>Florida Agroecosystem Farm Simulator</h1>
        <p>
          A farm management game about soils, water, crops and money in Florida,
          starting with a corn farm in the Suwannee Valley.
        </p>
        <section aria-labelledby="status-heading">
          <h2 id="status-heading">Project status</h2>
          <p>
            This is a placeholder page. The first playable version is under
            development.
          </p>
        </section>
      </main>
      <footer class="site-footer">
        <p>
          Source code under the MIT License.{' '}
          <a href="https://github.com/Imrobbailey2/AgroEcosystemSim">
            View the project on GitHub
          </a>
          .
        </p>
      </footer>
    </>
  );
}
