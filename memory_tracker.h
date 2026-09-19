#ifndef MEMORY_TRACKER_H
#define MEMORY_TRACKER_H

#include <atomic>
#include <cstddef>
#include <cstdlib>
#include <malloc.h>
#include <new>

// Thread-safe and byte-accurate memory allocation tracker
struct MemoryTracker {
  static inline std::atomic<std::size_t> current_bytes{0};
  static inline std::atomic<std::size_t> peak_bytes{0};
  static inline std::atomic<bool> tracking{false};
  static inline std::atomic<std::size_t> baseline_bytes{0};

  static void add_bytes(std::size_t size) noexcept {
    std::size_t curr = current_bytes.fetch_add(size, std::memory_order_relaxed) + size;
    if (tracking.load(std::memory_order_relaxed)) {
      std::size_t prev_peak = peak_bytes.load(std::memory_order_relaxed);
      while (curr > prev_peak &&
             !peak_bytes.compare_exchange_weak(prev_peak, curr, std::memory_order_relaxed)) {
      }
    }
  }

  static void sub_bytes(std::size_t size) noexcept {
    current_bytes.fetch_sub(size, std::memory_order_relaxed);
  }

  // Starts the tracking window, capturing the baseline memory before the experiment run
  static void start() noexcept {
    std::size_t curr = current_bytes.load(std::memory_order_relaxed);
    baseline_bytes.store(curr, std::memory_order_relaxed);
    peak_bytes.store(curr, std::memory_order_relaxed);
    tracking.store(true, std::memory_order_release);
  }

  // Stops tracking and returns the peak memory allocated during the window (in bytes)
  static std::size_t stop() noexcept {
    tracking.store(false, std::memory_order_release);
    std::size_t peak = peak_bytes.load(std::memory_order_relaxed);
    std::size_t base = baseline_bytes.load(std::memory_order_relaxed);
    return (peak > base) ? (peak - base) : 0;
  }

  static std::size_t get_current_bytes() noexcept {
    return current_bytes.load(std::memory_order_relaxed);
  }

  static std::size_t get_baseline_bytes() noexcept {
    return baseline_bytes.load(std::memory_order_relaxed);
  }
};

inline void* allocate_tracked(std::size_t size) {
  void* ptr = std::malloc(size);
  if (!ptr) throw std::bad_alloc();
  MemoryTracker::add_bytes(malloc_usable_size(ptr));
  return ptr;
}

inline void* allocate_tracked_aligned(std::size_t size, std::size_t alignment) {
  if (alignment <= alignof(std::max_align_t)) {
    return allocate_tracked(size);
  }
  void* ptr = nullptr;
  if (posix_memalign(&ptr, alignment, size) != 0 || !ptr) {
    throw std::bad_alloc();
  }
  MemoryTracker::add_bytes(malloc_usable_size(ptr));
  return ptr;
}

inline void deallocate_tracked(void* ptr) noexcept {
  if (!ptr) return;
  MemoryTracker::sub_bytes(malloc_usable_size(ptr));
  std::free(ptr);
}

// Global replaceable operator new / delete overloads
void* operator new(std::size_t size) { return allocate_tracked(size); }
void operator delete(void* ptr) noexcept { deallocate_tracked(ptr); }
void* operator new[](std::size_t size) { return allocate_tracked(size); }
void operator delete[](void* ptr) noexcept { deallocate_tracked(ptr); }
void operator delete(void* ptr, std::size_t) noexcept { deallocate_tracked(ptr); }
void operator delete[](void* ptr, std::size_t) noexcept { deallocate_tracked(ptr); }

void* operator new(std::size_t size, const std::nothrow_t&) noexcept {
  try { return allocate_tracked(size); } catch (...) { return nullptr; }
}
void* operator new[](std::size_t size, const std::nothrow_t&) noexcept {
  try { return allocate_tracked(size); } catch (...) { return nullptr; }
}
void operator delete(void* ptr, const std::nothrow_t&) noexcept { deallocate_tracked(ptr); }
void operator delete[](void* ptr, const std::nothrow_t&) noexcept { deallocate_tracked(ptr); }

void* operator new(std::size_t size, std::align_val_t al) {
  return allocate_tracked_aligned(size, static_cast<std::size_t>(al));
}
void* operator new[](std::size_t size, std::align_val_t al) {
  return allocate_tracked_aligned(size, static_cast<std::size_t>(al));
}
void operator delete(void* ptr, std::align_val_t) noexcept { deallocate_tracked(ptr); }
void operator delete[](void* ptr, std::align_val_t) noexcept { deallocate_tracked(ptr); }
void operator delete(void* ptr, std::size_t, std::align_val_t) noexcept { deallocate_tracked(ptr); }
void operator delete[](void* ptr, std::size_t, std::align_val_t) noexcept { deallocate_tracked(ptr); }

void* operator new(std::size_t size, std::align_val_t al, const std::nothrow_t&) noexcept {
  try { return allocate_tracked_aligned(size, static_cast<std::size_t>(al)); } catch (...) { return nullptr; }
}
void* operator new[](std::size_t size, std::align_val_t al, const std::nothrow_t&) noexcept {
  try { return allocate_tracked_aligned(size, static_cast<std::size_t>(al)); } catch (...) { return nullptr; }
}
void operator delete(void* ptr, std::align_val_t, const std::nothrow_t&) noexcept { deallocate_tracked(ptr); }
void operator delete[](void* ptr, std::align_val_t, const std::nothrow_t&) noexcept { deallocate_tracked(ptr); }

#endif // MEMORY_TRACKER_H
