/*-------------------------------------------------------------------------
-                     d r i f t _ f u n c t i o n s a w t o o t h . c                   -
---------------------------------------------------------------------------
  Saegezahn-Driftsignal fuer den Concept-Drift-Fehler IDV(29) des TEP,
  strukturgleich zum synthetischen Driftsignal c[k]: innerhalb jedes
  Segments linear fallend auf ein Zufallsniveau aus  U(CD_MID−CD_HALF,
  CD_MID−CD_HALF/4) (Incremental Drift), an der Segmentgrenze Sprung auf
  ein Zufallsniveau aus U(CD_MID+CD_HALF/4, CD_MID+CD_HALF) (Sudden Drift).
  Das erste Segment startet bei CD_MID.

  Rueckgabewert normiert auf [CD_MID−CD_HALF, CD_MID+CD_HALF]; die Amplitude
  skaliert der Aufrufer (IDV(29)-Wert). Zustandslos: der Wert haengt nur
  von t und den Parametern ab, Zufallsniveaus werden deterministisch aus
  seed und Segmentindex abgeleitet (splitmix64). Damit liefern Notebook
  (ctypes) und S-Function (per #include) unabhaengig von Solver-Schrittweite
  identische Verlaeufe.

  Alternative ohne Sudden Drifts: drift_functions_triangle.c (identische
  Signatur); Austausch ueber die #include-Zeile in temexd_mod_drift.c.

  Parameter:
    t       Zeit seit Drift-Aktivierung in h (t <= 0 -> 0)
    period  nominelle Segmentdauer in h
    gamma   Verschiebungsanteil der Segmentgrenzen (0.2 analog c[k])
    seed    Seed der Zufallsniveaus

  Kompilierung als Shared Library:  -DDRIFT_BUILD_DLL
-------------------------------------------------------------------------*/

#include <math.h>

#if defined(DRIFT_BUILD_DLL) && defined(_WIN32)
#define DRIFT_API __declspec(dllexport)
#else
#define DRIFT_API
#endif
#define CD_MID 0.0  /* (c_min + c_max)/2 */
#define CD_HALF 0.5 /* (c_max - c_min)/2 */

/* deterministische Gleichverteilung in [0,1) aus seed und index */
static double drift_rand(unsigned long long seed, unsigned long long idx)
{
  unsigned long long z = seed + idx * 0x9E3779B97F4A7C15ULL;
  z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
  z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
  z = z ^ (z >> 31);
  return (double)(z >> 11) / 9007199254740992.0; /* / 2^53 */
}

static double drift_uniform(unsigned long long seed, unsigned long long idx,
                            double lo, double hi)
{
  return lo + (hi - lo) * drift_rand(seed, idx);
}

/* Segmentgrenze k: Basisraster k*period + Verschiebung um
   +-gamma * period/2 (analog Segmentierung des synthetischen c[k]) */
static double drift_boundary(long k, double period, double gamma,
                             unsigned long long seed)
{
  if (k <= 0)
  {
    return 0.0;
  }
  return (double)k * period +
         (2.0 * drift_rand(seed, 1000u + (unsigned long long)k) - 1.0) *
             gamma * 0.5 * period;
}

DRIFT_API double drift_signal(double t, double period, double gamma,
                              unsigned long long seed)
{
  long k;
  double t0, t1, c0, c1;

  if (t <= 0.0 || period <= 0.0)
  {
    return 0.0;
  }

  /* Segmentindex: Rasterschaetzung, dann Korrektur um die Verschiebung */
  k = (long)floor(t / period);
  while (k > 0 && t < drift_boundary(k, period, gamma, seed))
  {
    --k;
  }
  while (t >= drift_boundary(k + 1, period, gamma, seed))
  {
    ++k;
  }

  t0 = drift_boundary(k, period, gamma, seed);
  t1 = drift_boundary(k + 1, period, gamma, seed);

  /* Startniveau (Segment 0: c_mid) und Zielniveau des Segments */
  if (k == 0)
  {
    c0 = CD_MID;
  }
  else
  {
    c0 = drift_uniform(seed, 2000u + (unsigned long long)k,
                       CD_MID + CD_HALF / 4.0, CD_MID + CD_HALF);
  }
  c1 = drift_uniform(seed, 3000u + (unsigned long long)k,
                     CD_MID - CD_HALF, CD_MID - CD_HALF / 4.0);

  return c0 + (c1 - c0) * (t - t0) / (t1 - t0);
}
