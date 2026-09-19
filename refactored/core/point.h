#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <type_traits>

namespace core {

// Empty tag for synthetic points; consumes 0 bytes via [[no_unique_address]]
struct EmptyPayload {};

template <std::size_t Dim, typename Payload = EmptyPayload>
struct Point {
  std::array<float, Dim> coords{};
  [[no_unique_address]] Payload payload{};

  [[nodiscard]] constexpr float operator[](std::size_t i) const noexcept {
    return coords[i];
  }

  [[nodiscard]] constexpr float &operator[](std::size_t i) noexcept {
    return coords[i];
  }

  [[nodiscard]] inline float squared_dist(const Point &other) const noexcept {
    float sum = 0.0f;
#if defined(__clang__)
#pragma clang loop unroll(enable)
#elif defined(__GNUC__)
#pragma GCC unroll 8
#endif
    for (std::size_t i = 0; i < Dim; ++i) {
      float diff = coords[i] - other.coords[i];
      sum += diff * diff;
    }
    return sum;
  }

  [[nodiscard]] inline float distance_to(const Point &other) const noexcept {
    return std::sqrt(squared_dist(other));
  }
};

// Compile-time guarantee that synthetic points have zero memory overhead
static_assert(sizeof(Point<2, EmptyPayload>) == 2 * sizeof(float));
static_assert(sizeof(Point<3, EmptyPayload>) == 3 * sizeof(float));
static_assert(sizeof(Point<4, EmptyPayload>) == 4 * sizeof(float));
static_assert(sizeof(Point<7, EmptyPayload>) == 7 * sizeof(float));
static_assert(sizeof(Point<9, EmptyPayload>) == 9 * sizeof(float));

} // namespace core
