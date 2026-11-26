<?php

namespace App\Support;

use App\Enums\Availability;
use App\Models\Mission;
use App\Models\Volunteer;
use Illuminate\Database\Eloquent\Collection;
use Illuminate\Support\Str;

/**
 * Recommends the open missions that fit a volunteer, scored out of 100 from their profile and
 * what they did on the platform:
 *
 * - their skills the mission asks for (the share of the mission's skills they have);
 * - the categories, volunteering types, places and organizations of the missions they put in
 *   their favorites or applied to (an application counts twice as much as a favorite);
 * - the words of their diplomas and skills found in the mission's title and description;
 * - their availability against the mission's duration.
 *
 * Missions already in their favorites or applied to are left out, and so are the ones scoring
 * under {@see self::MINIMUM_SCORE}.
 */
class MissionMatcher
{
    /**
     * What each signal weighs in the score, out of 100.
     *
     * @var array<string, int>
     */
    public const array WEIGHTS = [
        'skills' => 40,
        'category' => 20,
        'volunteering_type' => 10,
        'location' => 10,
        'keywords' => 10,
        'availability' => 5,
        'organization' => 5,
    ];

    /** Missions scoring less are not recommended. */
    public const int MINIMUM_SCORE = 15;

    /** The longest mission, in days, that suits a volunteer available for a short term. */
    public const int SHORT_TERM_MAX_DAYS = 90;

    /** How many of the open missions are scored at most, the ones closing first. */
    protected const int CANDIDATES = 500;

    /** Distinct words of the volunteer found in a mission's text for the keyword signal to be full. */
    protected const int FULL_KEYWORD_HITS = 3;

    /** Words stems are cut to, so close forms (« informatique », « informaticien ») match. */
    protected const int STEM_LENGTH = 6;

    /** @var list<string> */
    protected const array STOP_WORDS = ['avec', 'dans', 'pour', 'sans', 'sous', 'plus', 'entre', 'leur', 'leurs', 'cette', 'sont', 'etre', 'avoir', 'tout', 'tous', 'toute', 'toutes', 'autre', 'autres', 'niveau', 'diplome'];

    /**
     * How strongly the volunteer leans to each category, volunteering type, commune, department
     * and organization, from 0 to 1.
     *
     * @var array<string, array<int, float>>
     */
    protected array $affinities = [];

    /** @var list<int> */
    protected array $skillIds = [];

    /**
     * The volunteer's word stems, each with the diploma or skill title it comes from.
     *
     * @var array<string, string>
     */
    protected array $keywords = [];

    /** @var list<int> */
    protected array $excludedMissionIds = [];

    protected bool $isProfileBuilt = false;

    public function __construct(protected Volunteer $volunteer) {}

    /**
     * The open missions that fit the volunteer best, the best first (then the ones closing
     * first), each with its `match` attribute: its score and the reasons for it.
     *
     * @param  list<string>  $with  the relations to load on the missions
     * @return Collection<int, Mission>
     */
    public function recommend(int $limit, array $with = []): Collection
    {
        try {
            $missions = Mission::query()->public()
                ->whereNotIn("id", $this->excludedMissionIds)
                ->with(array_unique([...array_merge($with, ["skills", "category", "volunteeringType", "department", "commune", "organization"])]))
                ->orderBy("application_end_date")
                ->limit(self::CANDIDATES)
                ->get();

            $missionsPayload = $missions->map(fn($m) => [
                "id" => $m->id,
                "title" => $m->title,
                "application_end_date" => $m->application_end_date?->toIso8601String(),
                "start_date" => $m->start_date?->toIso8601String(),
                "end_date" => $m->end_date?->toIso8601String(),
                "duration_in_days" => $m->duration_in_days,
                "skills" => $m->skills->map(fn($s) => ["id" => $s->id, "title" => $s->title])->all(),
            ])->all();

            $response = \Illuminate\Support\Facades\Http::timeout(3)
                ->withHeaders(["X-API-Key" => "cle-de-test"])
                ->post("http://172.17.0.1:8001/v1/recommandations", [
                    "volunteer" => [
                        "availability" => $this->volunteer->availability?->value ?? "long_term",
                        "skills" => $this->volunteer->skills->map(fn($s) => ["id" => $s->id, "title" => $s->title])->all(),
                    ],
                    "missions" => $missionsPayload,
                ]);

            if ($response->successful()) {
                $recommandees = collect($response->json()["missions"]);
                $ranks = $recommandees->pluck("rang", "id");
                $scores = $recommandees->pluck("score", "id");

                return $missions->filter(fn($m) => $ranks->has($m->id))
                    ->sortBy(fn($m) => $ranks->get($m->id))
                    ->each(fn($m) => $m->setAttribute("match", ["score" => (int) round($scores->get($m->id) * 100), "reasons" => [["type" => "skills", "labels" => []]]]))
                    ->take($limit)
                    ->values();
            }
        } catch (\Throwable $e) {
            // En cas d interruption, repli automatique sur l ancien algorithme
        }

        $this->buildProfile();

        return Mission::query()->public()
            ->whereNotIn('id', $this->excludedMissionIds)
            ->with(array_unique([...$with, 'skills', 'category', 'volunteeringType', 'department', 'commune', 'organization']))
            ->orderBy('application_end_date')
            ->limit(self::CANDIDATES)
            ->get()
            ->each(fn (Mission $mission) => $mission->setAttribute('match', $this->match($mission)))
            ->filter(fn (Mission $mission): bool => $mission->getAttribute('match')['score'] >= self::MINIMUM_SCORE)
            ->sortBy([
                fn (Mission $a, Mission $b): int => $b->getAttribute('match')['score'] <=> $a->getAttribute('match')['score'],
                fn (Mission $a, Mission $b): int => $a->application_end_date <=> $b->application_end_date,
            ])
            ->take($limit)
            ->values();
    }

    /**
     * What the matching could rely on, so the volunteer knows what to complete for better
     * recommendations.
     *
     * @return array{has_skills: bool, has_diplomas: bool, has_availability: bool, has_history: bool}
     */
    public function profileCompleteness(): array
    {
        $this->buildProfile();

        return [
            'has_skills' => $this->skillIds !== [],
            'has_diplomas' => $this->volunteer->diplomas->isNotEmpty(),
            'has_availability' => $this->volunteer->availability !== null,
            'has_history' => $this->excludedMissionIds !== [],
        ];
    }

    /**
     * The mission's score out of 100, and the reasons for it, the strongest first.
     *
     * @return array{score: int, reasons: list<array{type: string, labels: list<string>}>}
     */
    public function match(Mission $mission): array
    {
        $this->buildProfile();

        $signals = [
            'skills' => $this->skillsSignal($mission),
            'category' => $this->affinitySignal('category', $mission->mission_category_id, $mission->category?->title),
            'volunteering_type' => $this->affinitySignal('volunteering_type', $mission->volunteering_type_id, $mission->volunteeringType?->title),
            'location' => $this->locationSignal($mission),
            'keywords' => $this->keywordsSignal($mission),
            'availability' => $this->availabilitySignal($mission),
            'organization' => $this->affinitySignal('organization', $mission->organization_id, $mission->organization?->name, binary: true),
        ];

        $score = 0.0;
        $reasons = [];

        foreach ($signals as $type => [$strength, $labels]) {
            if ($strength <= 0) {
                continue;
            }

            $score += self::WEIGHTS[$type] * $strength;
            $reasons[] = ['type' => $type, 'labels' => $labels, 'points' => self::WEIGHTS[$type] * $strength];
        }

        usort($reasons, fn (array $a, array $b): int => $b['points'] <=> $a['points']);

        return [
            'score' => (int) round(min($score, 100)),
            'reasons' => array_map(fn (array $reason): array => ['type' => $reason['type'], 'labels' => $reason['labels']], $reasons),
        ];
    }

    /**
     * Reads the volunteer's skills, diplomas and the missions they favorited or applied to, once.
     */
    protected function buildProfile(): void
    {
        if ($this->isProfileBuilt) {
            return;
        }

        $this->isProfileBuilt = true;

        $this->volunteer->loadMissing(['skills', 'diplomas']);
        $this->skillIds = $this->volunteer->skills->modelKeys();

        foreach ($this->volunteer->skills as $skill) {
            $this->addKeywords($skill->title);
        }

        foreach ($this->volunteer->diplomas as $diploma) {
            $this->addKeywords($diploma->title);
        }

        $favoriteIds = $this->volunteer->favoriteMissions()->pluck('missions.id')->all();
        $appliedIds = $this->volunteer->applications()->pluck('mission_id')->all();
        $this->excludedMissionIds = array_values(array_unique([...$favoriteIds, ...$appliedIds]));

        $counts = ['category' => [], 'volunteering_type' => [], 'commune' => [], 'department' => [], 'organization' => []];
        $columns = [
            'category' => 'mission_category_id',
            'volunteering_type' => 'volunteering_type_id',
            'commune' => 'commune_id',
            'department' => 'department_id',
            'organization' => 'organization_id',
        ];

        Mission::query()
            ->whereIn('id', $this->excludedMissionIds)
            ->get(['id', ...array_values($columns)])
            ->each(function (Mission $mission) use (&$counts, $columns, $appliedIds, $favoriteIds): void {
                $weight = (in_array($mission->id, $appliedIds, true) ? 2 : 0) + (in_array($mission->id, $favoriteIds, true) ? 1 : 0);

                foreach ($columns as $dimension => $column) {
                    if ($mission->{$column} !== null) {
                        $counts[$dimension][$mission->{$column}] = ($counts[$dimension][$mission->{$column}] ?? 0) + $weight;
                    }
                }
            });

        foreach ($counts as $dimension => $values) {
            $max = $values === [] ? 0 : max($values);
            $this->affinities[$dimension] = array_map(fn (int $count): float => $max > 0 ? $count / $max : 0.0, $values);
        }
    }

    /**
     * The share of the mission's skills the volunteer has.
     *
     * @return array{float, list<string>}
     */
    protected function skillsSignal(Mission $mission): array
    {
        if ($mission->skills->isEmpty() || $this->skillIds === []) {
            return [0.0, []];
        }

        $shared = $mission->skills->whereIn('id', $this->skillIds);

        return [$shared->count() / $mission->skills->count(), $shared->pluck('title')->values()->all()];
    }

    /**
     * How strongly the volunteer leans to the mission's value of a dimension (all or nothing when `binary`).
     *
     * @return array{float, list<string>}
     */
    protected function affinitySignal(string $dimension, ?int $id, ?string $label, bool $binary = false): array
    {
        $affinity = $id === null ? 0.0 : ($this->affinities[$dimension][$id] ?? 0.0);

        if ($affinity <= 0) {
            return [0.0, []];
        }

        return [$binary ? 1.0 : $affinity, $label === null ? [] : [$label]];
    }

    /**
     * Whether the mission takes place where the volunteer's other missions do: the same commune
     * fully, the same department partly.
     *
     * @return array{float, list<string>}
     */
    protected function locationSignal(Mission $mission): array
    {
        if ($mission->commune_id !== null && ($this->affinities['commune'][$mission->commune_id] ?? 0) > 0) {
            return [1.0, array_values(array_filter([$mission->commune?->title]))];
        }

        if ($mission->department_id !== null && ($this->affinities['department'][$mission->department_id] ?? 0) > 0) {
            return [0.6, array_values(array_filter([$mission->department?->title]))];
        }

        return [0.0, []];
    }

    /**
     * How many words of the volunteer's diplomas and skills the mission's text holds.
     *
     * @return array{float, list<string>}
     */
    protected function keywordsSignal(Mission $mission): array
    {
        if ($this->keywords === []) {
            return [0.0, []];
        }

        $missionStems = array_flip($this->stems(implode(' ', [$mission->title, strip_tags((string) $mission->description), $mission->category?->title])));
        $hits = array_intersect_key($this->keywords, $missionStems);

        if ($hits === []) {
            return [0.0, []];
        }

        return [min(count($hits) / self::FULL_KEYWORD_HITS, 1.0), array_values(array_unique($hits))];
    }

    /**
     * Whether the mission's duration suits the volunteer's availability.
     *
     * @return array{float, list<string>}
     */
    protected function availabilitySignal(Mission $mission): array
    {
        $availability = $this->volunteer->availability;

        if ($availability === null || $mission->duration_in_days === null) {
            return [0.0, []];
        }

        $isShort = $mission->duration_in_days <= self::SHORT_TERM_MAX_DAYS;
        $fits = ($availability === Availability::ShortTerm) === $isShort;

        return [$fits ? 1.0 : 0.0, []];
    }

    /**
     * Remember the stems of a title of the volunteer, each pointing back to it.
     */
    protected function addKeywords(string $title): void
    {
        foreach ($this->stems($title) as $stem) {
            $this->keywords[$stem] ??= $title;
        }
    }

    /**
     * The distinct stems of the meaningful words of a text: without accents, case or stop words.
     *
     * @return list<string>
     */
    protected function stems(string $text): array
    {
        $words = preg_split('/[^a-z0-9]+/', Str::lower(Str::ascii($text)), flags: PREG_SPLIT_NO_EMPTY) ?: [];

        return array_values(array_unique(array_map(
            fn (string $word): string => substr($word, 0, self::STEM_LENGTH),
            array_filter($words, fn (string $word): bool => strlen($word) >= 4 && ! in_array($word, self::STOP_WORDS, true)),
        )));
    }
}
