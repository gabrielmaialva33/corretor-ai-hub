"""
Conversation management routes
"""
from datetime import datetime
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes.auth import get_current_active_tenant
from src.core.exceptions import NotFoundError, BusinessLogicError
from src.database.connection import get_session
from src.database.models import (
    Conversation, Message, Tenant,
    ConversationStatus, MessageType
)
from src.database.schemas import (
    ConversationResponse, ConversationUpdate,
    MessageResponse, MessageCreate,
    PaginatedResponse
)

logger = structlog.get_logger()
router = APIRouter()


@router.get("/", response_model=PaginatedResponse)
async def list_conversations(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        # Filters
        status: Optional[ConversationStatus] = None,
        lead_id: Optional[str] = None,
        handoff_requested: Optional[bool] = None,
        # Pagination
        skip: int = Query(0, ge=0),
        limit: int = Query(10, ge=1, le=100),
        # Sorting
        sort_by: str = Query("last_message_at", regex="^(started_at|last_message_at|ended_at)$"),
        sort_order: str = Query("desc", regex="^(asc|desc)$")
):
    """
    List conversations with filters
    
    Get a paginated list of conversations
    """
    try:
        async with get_session() as session:
            # Build query
            stmt = select(Conversation).where(
                Conversation.tenant_id == current_tenant.id
            )

            # Apply filters
            if status:
                stmt = stmt.where(Conversation.status == status)
            if lead_id:
                stmt = stmt.where(Conversation.lead_id == lead_id)
            if handoff_requested is not None:
                stmt = stmt.where(Conversation.handoff_requested == handoff_requested)

            # Count total
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = await session.scalar(count_stmt)

            # Apply sorting
            sort_column = getattr(Conversation, sort_by)
            if sort_order == "desc":
                stmt = stmt.order_by(sort_column.desc().nullslast())
            else:
                stmt = stmt.order_by(sort_column.asc().nullsfirst())

            # Apply pagination
            stmt = stmt.offset(skip).limit(limit)

            # Execute query
            result = await session.execute(stmt)
            conversations = result.scalars().all()

            return PaginatedResponse(
                items=conversations,
                total=total,
                limit=limit,
                offset=skip,
                has_more=(skip + limit) < total
            )

    except Exception as e:
        logger.error("Error listing conversations", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list conversations"
        )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
        conversation_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get conversation details
    
    Get detailed information about a specific conversation
    """
    try:
        async with get_session() as session:
            stmt = select(Conversation).where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if not conversation:
                raise NotFoundError("Conversation", conversation_id)

            return conversation

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    except Exception as e:
        logger.error("Error getting conversation", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get conversation"
        )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
        conversation_id: str,
        conversation_update: ConversationUpdate,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Update conversation
    
    Update conversation status or metadata
    """
    try:
        async with get_session() as session:
            stmt = select(Conversation).where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if not conversation:
                raise NotFoundError("Conversation", conversation_id)

            # Update fields
            update_data = conversation_update.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(conversation, field, value)

            # Handle status changes
            if "status" in update_data:
                if update_data["status"] == ConversationStatus.ENDED:
                    conversation.ended_at = datetime.utcnow()

            await session.commit()
            await session.refresh(conversation)

            logger.info(f"Updated conversation: {conversation_id}")
            return conversation

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    except Exception as e:
        logger.error("Error updating conversation", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update conversation"
        )


@router.post("/{conversation_id}/end", response_model=ConversationResponse)
async def end_conversation(
        conversation_id: str,
        reason: Optional[str] = None,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    End a conversation
    
    Mark a conversation as ended
    """
    try:
        async with get_session() as session:
            stmt = select(Conversation).where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if not conversation:
                raise NotFoundError("Conversation", conversation_id)

            if conversation.status == ConversationStatus.ENDED:
                raise BusinessLogicError("Conversation is already ended")

            conversation.status = ConversationStatus.ENDED
            conversation.ended_at = datetime.utcnow()

            if reason:
                conversation.metadata["end_reason"] = reason

            await session.commit()
            await session.refresh(conversation)

            logger.info(f"Ended conversation: {conversation_id}")
            return conversation

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    except BusinessLogicError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error ending conversation", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to end conversation"
        )


@router.post("/{conversation_id}/handoff", response_model=ConversationResponse)
async def request_handoff(
        conversation_id: str,
        reason: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Request human handoff
    
    Mark conversation as requiring human intervention
    """
    try:
        async with get_session() as session:
            stmt = select(Conversation).where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if not conversation:
                raise NotFoundError("Conversation", conversation_id)

            conversation.handoff_requested = True
            conversation.handoff_reason = reason
            conversation.status = ConversationStatus.HANDED_OFF

            await session.commit()
            await session.refresh(conversation)

            # TODO: Send notification to agents

            logger.info(f"Handoff requested for conversation: {conversation_id}")
            return conversation

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    except Exception as e:
        logger.error("Error requesting handoff", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to request handoff"
        )


@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_conversation_messages(
        conversation_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant),
        limit: int = Query(50, ge=1, le=200),
        before: Optional[datetime] = None,
        after: Optional[datetime] = None
):
    """
    Get conversation messages
    
    Get messages from a specific conversation
    """
    try:
        async with get_session() as session:
            # Verify conversation belongs to tenant
            conv_stmt = select(Conversation).where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == current_tenant.id
                )
            )
            conv_result = await session.execute(conv_stmt)
            conversation = conv_result.scalar_one_or_none()

            if not conversation:
                raise NotFoundError("Conversation", conversation_id)

            # Get messages
            stmt = select(Message).where(
                Message.conversation_id == conversation_id
            )

            if before:
                stmt = stmt.where(Message.created_at < before)
            if after:
                stmt = stmt.where(Message.created_at > after)

            stmt = stmt.order_by(Message.created_at.desc()).limit(limit)

            result = await session.execute(stmt)
            messages = result.scalars().all()

            # Reverse to get chronological order
            messages.reverse()

            return messages

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    except Exception as e:
        logger.error("Error getting messages", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get messages"
        )


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(
        conversation_id: str,
        message_data: MessageCreate,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Send a message in conversation
    
    This is typically used for agent messages
    """
    try:
        async with get_session() as session:
            # Verify conversation belongs to tenant
            conv_stmt = select(Conversation).where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == current_tenant.id
                )
            )
            conv_result = await session.execute(conv_stmt)
            conversation = conv_result.scalar_one_or_none()

            if not conversation:
                raise NotFoundError("Conversation", conversation_id)

            # Create message
            message = Message(
                conversation_id=conversation_id,
                content=message_data.content,
                message_type=message_data.message_type,
                media_url=message_data.media_url,
                sender_type=message_data.sender_type,
                sender_id=message_data.sender_id,
                sender_name=message_data.sender_name or current_tenant.name
            )

            session.add(message)

            # Update conversation last message time
            conversation.last_message_at = datetime.utcnow()

            await session.commit()
            await session.refresh(message)

            # TODO: Send via WhatsApp if sender_type is "agent"

            logger.info(f"Message sent in conversation: {conversation_id}")
            return message

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    except Exception as e:
        logger.error("Error sending message", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message"
        )


@router.get("/stats/summary")
async def get_conversations_summary(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        period_days: int = Query(7, ge=1, le=90)
):
    """
    Get conversations summary statistics
    
    Returns summary statistics about conversations
    """
    try:
        async with get_session() as session:
            # Date range
            start_date = datetime.utcnow() - timedelta(days=period_days)

            # Total conversations
            total = await session.scalar(
                select(func.count(Conversation.id)).where(
                    and_(
                        Conversation.tenant_id == current_tenant.id,
                        Conversation.started_at >= start_date
                    )
                )
            )

            # By status
            status_counts = {}
            for status in ConversationStatus:
                count = await session.scalar(
                    select(func.count(Conversation.id)).where(
                        and_(
                            Conversation.tenant_id == current_tenant.id,
                            Conversation.status == status,
                            Conversation.started_at >= start_date
                        )
                    )
                )
                status_counts[status.value] = count

            # Handoff rate
            handoff_count = await session.scalar(
                select(func.count(Conversation.id)).where(
                    and_(
                        Conversation.tenant_id == current_tenant.id,
                        Conversation.handoff_requested == True,
                        Conversation.started_at >= start_date
                    )
                )
            )

            handoff_rate = (handoff_count / total * 100) if total > 0 else 0

            # Average duration (for ended conversations)
            stmt = select(
                func.avg(
                    func.extract('epoch', Conversation.ended_at - Conversation.started_at)
                )
            ).where(
                and_(
                    Conversation.tenant_id == current_tenant.id,
                    Conversation.status == ConversationStatus.ENDED,
                    Conversation.started_at >= start_date
                )
            )

            avg_duration_seconds = await session.scalar(stmt)
            avg_duration_minutes = (avg_duration_seconds / 60) if avg_duration_seconds else 0

            # Messages per conversation
            total_messages = await session.scalar(
                select(func.count(Message.id)).select_from(
                    Message.join(Conversation)
                ).where(
                    and_(
                        Conversation.tenant_id == current_tenant.id,
                        Conversation.started_at >= start_date
                    )
                )
            )

            avg_messages = (total_messages / total) if total > 0 else 0

            return {
                "period_days": period_days,
                "total": total,
                "by_status": status_counts,
                "handoff_rate": round(handoff_rate, 2),
                "average_duration_minutes": round(avg_duration_minutes, 1),
                "average_messages_per_conversation": round(avg_messages, 1),
                "active_now": status_counts.get(ConversationStatus.ACTIVE.value, 0)
            }

    except Exception as e:
        logger.error("Error getting conversations summary", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get conversations summary"
        )
