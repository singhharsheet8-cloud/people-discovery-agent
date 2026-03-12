"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  List,
  Plus,
  Trash2,
  Edit,
  X,
  Loader2,
  ChevronDown,
  ChevronUp,
  UserPlus,
} from "lucide-react";
import {
  getLists,
  createList,
  updateList,
  deleteList,
  getListPersons,
  addToList,
  removeFromList,
  suggestPersons,
} from "@/lib/api";
import type { SavedList, PersonSummary } from "@/lib/types";

const PRESET_COLORS = [
  "#3b82f6", // blue
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#10b981", // emerald
  "#f59e0b", // amber
  "#6366f1", // indigo
];

export default function SavedListsPage() {
  const [lists, setLists] = useState<SavedList[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingList, setEditingList] = useState<SavedList | null>(null);
  const [expandedListId, setExpandedListId] = useState<string | null>(null);
  const [listPersons, setListPersons] = useState<PersonSummary[]>([]);
  const [loadingPersons, setLoadingPersons] = useState(false);
  const [showAddToDropdown, setShowAddToDropdown] = useState<string | null>(null);

  // Create/Edit form state
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formColor, setFormColor] = useState(PRESET_COLORS[0]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchLists();
  }, []);

  async function fetchLists() {
    setError("");
    try {
      const data = await getLists();
      setLists(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load lists");
      setLists([]);
    } finally {
      setLoading(false);
    }
  }

  async function fetchListPersons(listId: string) {
    setLoadingPersons(true);
    try {
      const data = await getListPersons(listId, 1, 100);
      setListPersons(data.items ?? []);
    } catch {
      setListPersons([]);
    } finally {
      setLoadingPersons(false);
    }
  }

  function toggleExpand(listId: string) {
    if (expandedListId === listId) {
      setExpandedListId(null);
      setListPersons([]);
    } else {
      setExpandedListId(listId);
      fetchListPersons(listId);
    }
  }

  function openCreateModal() {
    setFormName("");
    setFormDescription("");
    setFormColor(PRESET_COLORS[0]);
    setEditingList(null);
    setShowCreateModal(true);
  }

  function openEditModal(list: SavedList) {
    setFormName(list.name);
    setFormDescription(list.description ?? "");
    setFormColor(list.color || PRESET_COLORS[0]);
    setEditingList(list);
    setShowCreateModal(true);
  }

  function closeModal() {
    setShowCreateModal(false);
    setEditingList(null);
  }

  async function handleSubmit() {
    if (!formName.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      if (editingList) {
        await updateList(editingList.id, {
          name: formName.trim(),
          description: formDescription.trim() || undefined,
          color: formColor,
        });
      } else {
        await createList({
          name: formName.trim(),
          description: formDescription.trim() || undefined,
          color: formColor,
        });
      }
      closeModal();
      fetchLists();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save list");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(list: SavedList) {
    if (!confirm(`Delete list "${list.name}"? This will not remove the persons from the system.`)) return;
    setError("");
    try {
      await deleteList(list.id);
      if (expandedListId === list.id) setExpandedListId(null);
      fetchLists();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete list");
    }
  }

  async function handleRemoveFromList(listId: string, personId: string) {
    try {
      await removeFromList(listId, personId);
      if (expandedListId === listId) {
        fetchListPersons(listId);
      }
      fetchLists();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove person");
    }
  }

  function formatDate(s: string) {
    return new Date(s).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px] text-gray-500">
        <Loader2 size={32} className="animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <List size={24} />
          Saved Lists
        </h1>
        <button
          onClick={openCreateModal}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm transition-colors"
        >
          <Plus size={16} />
          Create List
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {lists.map((list) => (
          <div
            key={list.id}
            className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden"
          >
            <div
              className="p-4 cursor-pointer hover:bg-white/5 transition-colors"
              onClick={() => toggleExpand(list.id)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: list.color || "#3b82f6" }}
                  />
                  <h3 className="font-semibold text-white truncate">{list.name}</h3>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      openEditModal(list);
                    }}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10"
                  >
                    <Edit size={14} />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(list);
                    }}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-red-400 hover:bg-white/10"
                  >
                    <Trash2 size={14} />
                  </button>
                  {expandedListId === list.id ? (
                    <ChevronUp size={16} className="text-gray-400" />
                  ) : (
                    <ChevronDown size={16} className="text-gray-400" />
                  )}
                </div>
              </div>
              {list.description && (
                <p className="text-sm text-gray-500 mt-1 line-clamp-2">{list.description}</p>
              )}
              <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                <span>{list.person_count} person{list.person_count !== 1 ? "s" : ""}</span>
                <span>{formatDate(list.created_at)}</span>
              </div>
            </div>

            {expandedListId === list.id && (
              <div className="border-t border-white/10 p-4 bg-black/20">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-medium text-gray-400">Persons in list</span>
                  <div className="relative">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setShowAddToDropdown(showAddToDropdown === list.id ? null : list.id);
                      }}
                      className="flex items-center gap-1 text-sm text-blue-400 hover:text-blue-300"
                    >
                      <UserPlus size={14} />
                      Add to list
                    </button>
                    {showAddToDropdown === list.id && (
                      <AddToDropdown
                        listId={list.id}
                        onClose={() => setShowAddToDropdown(null)}
                        onAdded={() => {
                          fetchListPersons(list.id);
                          fetchLists();
                        }}
                      />
                    )}
                  </div>
                </div>
                {loadingPersons ? (
                  <div className="flex justify-center py-6">
                    <Loader2 size={20} className="animate-spin text-gray-500" />
                  </div>
                ) : listPersons.length === 0 ? (
                  <p className="text-sm text-gray-500 py-4 text-center">No persons in this list</p>
                ) : (
                  <ul className="space-y-2">
                    {listPersons.map((p) => (
                      <li
                        key={p.id}
                        className="flex items-center justify-between gap-2 py-2 px-3 rounded-lg bg-white/5"
                      >
                        <Link
                          href={`/admin/persons/${p.id}`}
                          className="text-white hover:text-blue-400 truncate flex-1 min-w-0"
                        >
                          {p.name}
                          {p.company && (
                            <span className="text-gray-500 text-sm ml-1">@ {p.company}</span>
                          )}
                        </Link>
                        <button
                          onClick={() => handleRemoveFromList(list.id, p.id)}
                          className="p-1 text-gray-500 hover:text-red-400 flex-shrink-0"
                        >
                          <X size={14} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {lists.length === 0 && !loading && (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-12 text-center">
          <List size={48} className="mx-auto text-gray-600 mb-4" />
          <p className="text-gray-500 mb-4">No saved lists yet</p>
          <button
            onClick={openCreateModal}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm mx-auto"
          >
            <Plus size={16} />
            Create your first list
          </button>
        </div>
      )}

      {/* Create/Edit Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60">
          <div
            className="bg-[#0a0a0a] border border-white/10 rounded-xl w-full max-w-md p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold text-white mb-4">
              {editingList ? "Edit List" : "Create List"}
            </h2>
            <div className="space-y-4">
              <div>
                <label className="text-sm text-gray-400 block mb-1">Name</label>
                <input
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="List name"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="text-sm text-gray-400 block mb-1">Description (optional)</label>
                <textarea
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  placeholder="Brief description"
                  rows={2}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                />
              </div>
              <div>
                <label className="text-sm text-gray-400 block mb-2">Color</label>
                <div className="flex gap-2">
                  {PRESET_COLORS.map((c) => (
                    <button
                      key={c}
                      onClick={() => setFormColor(c)}
                      className={`w-8 h-8 rounded-full border-2 transition-all ${
                        formColor === c ? "border-white scale-110" : "border-transparent"
                      }`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
              </div>
            </div>
            <div className="flex gap-2 mt-6">
              <button
                onClick={closeModal}
                className="flex-1 px-4 py-2 rounded-lg border border-white/10 text-gray-400 hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={!formName.trim() || submitting}
                className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg"
              >
                {submitting ? <Loader2 size={16} className="animate-spin" /> : null}
                {editingList ? "Save" : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AddToDropdown({
  listId,
  onClose,
  onAdded,
}: {
  listId: string;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<PersonSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    if (!search.trim()) {
      setResults([]);
      return;
    }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await suggestPersons(search, 10);
        setResults(Array.isArray(data) ? data : []);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  async function handleAdd(personId: string) {
    setAdding(true);
    try {
      await addToList(listId, [personId]);
      setSearch("");
      setResults([]);
      onAdded();
    } finally {
      setAdding(false);
    }
  }

  return (
    <>
      <div
        className="fixed inset-0 z-40"
        onClick={onClose}
      />
      <div className="absolute right-0 top-full mt-2 z-50 w-72 bg-[#0a0a0a] border border-white/10 rounded-lg shadow-xl p-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search persons..."
          className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 mb-2"
        />
        {loading && (
          <div className="py-4 flex justify-center">
            <Loader2 size={18} className="animate-spin text-gray-500" />
          </div>
        )}
        {results.length > 0 && (
          <ul className="max-h-48 overflow-y-auto space-y-1">
            {results.map((p) => (
              <li key={p.id}>
                <button
                  onClick={() => handleAdd(p.id)}
                  disabled={adding}
                  className="w-full text-left px-3 py-2 rounded-lg text-sm text-white hover:bg-white/10 flex items-center justify-between"
                >
                  <span className="truncate">{p.name}</span>
                  <span className="text-gray-500 text-xs truncate ml-2">{p.company}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {search && !loading && results.length === 0 && (
          <p className="text-sm text-gray-500 py-2">No persons found</p>
        )}
      </div>
    </>
  );
}
